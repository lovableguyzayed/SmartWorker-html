# Setting up a company on a live deployment

The seeding script in `tools/seed_uttaranchal.py` needs a shell and a
database connection string. The owner of a hosted deployment has neither —
that is the whole point of a hosted deployment — so the same code is
reachable over HTTP once, behind a token that exists only while somebody
has deliberately put it in the environment.

**It deletes every company, login, worker and record on the database
first.** That is what it is for: the company has to come out clean. Take a
backup if anything on there matters.

## Doing it

1. **Set the token.** In Render: your service → **Environment** → **Add
   Environment Variable**.

   | Key | Value |
   | --- | --- |
   | `SETUP_TOKEN` | any string of 16 characters or more |

   Make it something nobody would guess — it is the only credential on the
   route. Save; Render redeploys, which takes a minute or two.

2. **Open the link**, on a phone or anywhere:

   ```
   https://<your-app>.onrender.com/__setup/<the token you set>
   ```

   The page lists what is on the database now and what it will build.
   Nothing is written by opening it.

3. **Type `WIPE AND SETUP`** in the box and press the button. It runs in a
   few seconds and shows what it created.

4. **Remove `SETUP_TOKEN`** from the environment and let it redeploy.
   While it is set, anyone holding that link can wipe the database again.
   The route returns 404 the moment the variable is gone.

## What it builds

* **Uttaranchal Stone Crusher**, with `Javed` as the administrator —
  password is the mobile number on that account
* Javed also on the payroll as a monthly-salaried employee: joined
  7 August, ₹23,000 a month on a 26-day basis, paid only for days worked in
  the joining month, 19 October a closure day, on nights from 21 October,
  and ₹20,000 handed over on 22 October
* Ten more workers — one of every pay type and employment type the app
  handles, so each screen has something real on it
* A mukadam login, `imran`, with attendance and transaction powers, for
  showing what a supervisor sees
* Attendance from each joining date to today, and money of each kind: an
  advance, a bonus, wages paid in cash, and wages paid by UPI with the UTR
  against them
* Two of the crew left unmarked today, so there is something real to scan

## The figures to expect

The account is set up to clear the **oldest unpaid month first**, because
nothing had been settled since August and the ₹20,000 handed over on
22 October is the first of those wages arriving, not an advance on October.
Javed's running account therefore reads:

| Month | Earned | Wages paid | Still owed |
| --- | --- | --- | --- |
| August 2026 | ₹22,125 | ₹20,000 | ₹2,125 |
| September 2026 | ₹23,000 | — | ₹25,125 |
| October 2026 | ₹23,000 | — | **₹48,125** |

August is 25 working days of a ₹23,000/26 month. Switching **Settings →
How payments are counted** to *the month it was paid in* moves the ₹20,000
onto October — August then shows its whole ₹22,125 and October reads
₹3,000 for the month. The total is ₹48,125 either way: the setting decides
which month shows the arrears, never how much there is. Nothing in the
database changes, so it is safe to switch during a demo and switch back.

The column's own default is `month`, which is what the app did before the
choice existed, so no other database's figures move. Only this account is
set deliberately.

## If you would rather not have the route at all

Two alternatives, both without this one:

* **Register normally** at `/register`. No SMS provider is configured, so
  the OTP is only written to the server log — Render → your service →
  **Logs**, search for `Registration OTP`. You get an empty company and log
  in by email.
* **Run the script** from a machine with the connection string:

  ```sh
  DATABASE_URL='<the connection string>' python tools/seed_uttaranchal.py
  DATABASE_URL='<the connection string>' python tools/seed_uttaranchal.py --apply
  ```

  Without `--apply` it only reports. It refuses a database holding the test
  fixture unless `--force` is passed as well, because seeding the
  development database makes every suite fail on the login screen.
