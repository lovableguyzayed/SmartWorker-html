package com.smartworker.bridge;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;

import androidx.core.content.FileProvider;

import org.apache.cordova.CallbackContext;
import org.apache.cordova.CordovaPlugin;
import org.json.JSONArray;
import org.json.JSONException;

import java.io.File;
import java.io.IOException;

/**
 * Two small things the app's own pages need from Android.
 *
 * 1. The bridge, for the deployed site and only for it. Cordova's default
 *    lets only the launch page (https://localhost/...) talk to native code.
 *    Returning null for every other URL keeps that default, so nothing else
 *    the WebView might show gains access.
 *
 * 2. "share": hand a file the app has just saved to Android's share sheet,
 *    so a payslip can go straight to WhatsApp. The WebView cannot share
 *    files itself (no Web Share API in an Android WebView).
 */
public class RemoteBridge extends CordovaPlugin {

    private String allowedPrefix() {
        String origin = preferences.getString("RemoteBridgeOrigin", "");
        if (origin == null || origin.isEmpty()) {
            return null;
        }
        // "https://example.com" must not also match "https://example.com.evil.net".
        return origin.endsWith("/") ? origin : origin + "/";
    }

    @Override
    public Boolean shouldAllowBridgeAccess(String url) {
        String prefix = allowedPrefix();
        if (prefix != null && url != null && url.startsWith(prefix)) {
            return true;
        }
        return null;
    }

    @Override
    public boolean execute(String action, JSONArray args, final CallbackContext callback)
            throws JSONException {
        if (!"share".equals(action)) {
            return false;
        }
        final String fileUrl = args.getString(0);
        final String mime = args.optString(1, "*/*");
        final String text = args.optString(2, "");

        cordova.getThreadPool().execute(() -> {
            try {
                Context ctx = cordova.getContext();
                File file = new File(Uri.parse(fileUrl).getPath());
                if (!file.isFile()) {
                    callback.error("No such file: " + fileUrl);
                    return;
                }
                // Only what the app itself wrote: its own storage folders.
                // Without this a page could ask to share any readable file.
                if (!insideAppStorage(ctx, file)) {
                    callback.error("Not an app file: " + fileUrl);
                    return;
                }
                // The provider cordova-plugin-file-opener2 declares; its paths
                // cover the folders cordova-plugin-file saves into.
                Uri uri = FileProvider.getUriForFile(
                        ctx, ctx.getPackageName() + ".fileOpener2.provider", file);

                Intent send = new Intent(Intent.ACTION_SEND);
                send.setType(mime);
                send.putExtra(Intent.EXTRA_STREAM, uri);
                if (!text.isEmpty()) {
                    send.putExtra(Intent.EXTRA_TEXT, text);
                }
                send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                final Intent chooser = Intent.createChooser(send, null);
                chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);

                cordova.getActivity().runOnUiThread(() -> {
                    try {
                        cordova.getActivity().startActivity(chooser);
                        callback.success();
                    } catch (Exception e) {
                        callback.error(e.getMessage());
                    }
                });
            } catch (Exception e) {
                callback.error(e.getMessage());
            }
        });
        return true;
    }

    private static boolean insideAppStorage(Context ctx, File file) throws IOException {
        String path = file.getCanonicalPath();
        File[] roots = new File[] {
            ctx.getFilesDir(), ctx.getCacheDir(),
            ctx.getExternalFilesDir(null), ctx.getExternalCacheDir(),
        };
        for (File root : roots) {
            if (root != null && path.startsWith(root.getCanonicalPath() + File.separator)) {
                return true;
            }
        }
        return false;
    }
}
