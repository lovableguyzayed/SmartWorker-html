"""Supabase Storage backend for image uploads.

When SUPABASE_URL and SUPABASE_SERVICE_KEY are set, worker profile photos and
company logos are uploaded to a public Supabase Storage bucket and only the
public URL is stored in the database — so images survive Render restarts and
redeploys (Render's local filesystem is ephemeral).

Without those variables the app falls back to saving files under
static/uploads/ exactly as before (local development, preview environments).

Uses Supabase's plain REST API over stdlib urllib — no extra dependencies.
The service_role key must NEVER be exposed to the client; it is used
server-side only.
"""
import json
import logging
import mimetypes
import os
import urllib.error
import urllib.request

SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or ''
BUCKET = os.environ.get('SUPABASE_STORAGE_BUCKET', 'smartworker-media')

_bucket_ready = False


def storage_enabled():
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _request(method, path, data=None, content_type='application/json', timeout=30):
    req = urllib.request.Request(
        SUPABASE_URL + path,
        data=data,
        method=method,
        headers={
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
            'apikey': SUPABASE_SERVICE_KEY,
            'Content-Type': content_type,
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def ensure_bucket():
    """Create the public bucket if it doesn't exist, and force an existing one
    public. Idempotent. The public check matters: a bucket created by hand in
    the Supabase dashboard defaults to PRIVATE, and then every upload succeeds
    while every public image URL returns 400 — photos 'save' but never display."""
    global _bucket_ready
    if _bucket_ready or not storage_enabled():
        return
    payload = json.dumps({'id': BUCKET, 'name': BUCKET, 'public': True}).encode()
    try:
        _request('POST', '/storage/v1/bucket', data=payload)
        logging.info("Created Supabase Storage bucket '%s'", BUCKET)
    except urllib.error.HTTPError as e:
        # 400/409 = bucket already exists — make sure it is public.
        if e.code not in (400, 409):
            raise
        try:
            with _request('GET', f'/storage/v1/bucket/{BUCKET}') as resp:
                info = json.loads(resp.read().decode() or '{}')
            if not info.get('public'):
                _request('PUT', f'/storage/v1/bucket/{BUCKET}',
                         data=json.dumps({'id': BUCKET, 'public': True}).encode())
                logging.warning(
                    "Supabase Storage bucket '%s' was PRIVATE — switched it to "
                    "public so stored image URLs work.", BUCKET)
        except Exception as check_exc:
            logging.warning("Could not verify bucket visibility: %s", check_exc)
    _bucket_ready = True


def public_url(object_path):
    return f'{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{object_path}'


def upload_image(object_path, data, content_type=None):
    """Upload bytes to the bucket (upsert) and return the public URL."""
    ensure_bucket()
    if not content_type:
        content_type = mimetypes.guess_type(object_path)[0] or 'application/octet-stream'
    req = urllib.request.Request(
        f'{SUPABASE_URL}/storage/v1/object/{BUCKET}/{object_path}',
        data=data,
        method='POST',
        headers={
            'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
            'apikey': SUPABASE_SERVICE_KEY,
            'Content-Type': content_type,
            'x-upsert': 'true',
        },
    )
    urllib.request.urlopen(req, timeout=60)
    return public_url(object_path)


def migrate_local_uploads(app, db):
    """One-time move of images stored under static/uploads/ into Supabase
    Storage. Rewrites the stored paths to public URLs. Safe to re-run: only
    rows still pointing at local paths (whose files exist) are touched."""
    if not storage_enabled():
        return
    from models import Worker, CompanySetting

    migrated = 0

    def _migrate_path(local_url, prefix):
        # local_url looks like '/static/uploads/workers/AB123_xxx.jpg'
        marker = '/static/uploads/'
        if not local_url or marker not in local_url:
            return None
        rel = local_url.split(marker, 1)[1]
        file_path = os.path.join(app.static_folder, 'uploads', *rel.split('/'))
        if not os.path.isfile(file_path):
            return None
        with open(file_path, 'rb') as fh:
            data = fh.read()
        return upload_image(rel, data)

    try:
        for worker in Worker.query.filter(Worker.profile_image.like('%/static/uploads/%')).all():
            new_url = _migrate_path(worker.profile_image, 'workers')
            if new_url:
                worker.profile_image = new_url
                migrated += 1
        company = CompanySetting.query.first()
        if company and company.logo and '/static/uploads/' in company.logo:
            new_url = _migrate_path(company.logo, 'company')
            if new_url:
                company.logo = new_url
                migrated += 1
        if migrated:
            db.session.commit()
            logging.info('Migrated %d image(s) from static/uploads to Supabase Storage', migrated)
    except Exception as e:
        db.session.rollback()
        logging.warning('Image migration to Supabase Storage skipped/failed: %s', e)
