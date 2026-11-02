#!/usr/bin/env python3
"""
WS1 daily-word fetcher.

Once a day, this script:
  1. Waits a random amount of time (so the real fetch lands at an unpredictable
     moment inside a window, not at a fixed second every day).
  2. Fetches that day's NYT Wordle answer from NYT's own API.
  3. Encrypts it with WS1's cipher (the same encryptWord() in index.html) --
     the plaintext answer is never written to disk or committed anywhere.
  4. Writes daily.json (just {"date": ..., "code": ...}) into the WS1 repo.
  5. Commits and pushes it, so captcraig.net/WS1/daily.json picks it up.

Run from cron once a day, near the START of your acquisition window (e.g.
3:00 AM Pacific = 6:00 AM Eastern). The script's own sleep spreads the real
fetch across the rest of the window on its own.

Usage:
    python3 daily_fetch.py            # normal run (sleeps, then fetches)
    python3 daily_fetch.py --now      # skip the sleep, for testing
"""
import json
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# ---- adjust this to wherever your WS1 repo actually lives ----
REPO_DIR = "/Users/craignelson/Projects/WS1"
OUTFILE = f"{REPO_DIR}/daily.json"

# How long the acquisition window is, in minutes, starting from whenever cron
# fires this script. 180 = 3 hours (e.g. 6-9 AM Eastern if cron fires at 6 AM).
WINDOW_MINUTES = 180

# ---- cipher: exact port of encryptWord() in index.html ----
CIPHER_P = [2, 3, 5, 7, 11]
_a, _b = "craig", "cigar"
CIPHER_PERM = [_a.index(ch) for ch in _b]
CIPHER_K = [
    (ord("craig"[j]) - 96) * CIPHER_P[j] + (ord("cigar"[j]) - 97) * CIPHER_P[4 - j]
    for j in range(5)
]
CIPHER_SEED = 13


def _md(n):
    return ((n % 26) + 26) % 26


def encrypt_word(w):
    x = [ord(ch) - 97 for ch in w]
    c = [0] * 5
    prev = CIPHER_SEED
    for j in range(5):
        c[j] = _md(x[CIPHER_PERM[j]] + CIPHER_K[j] + prev * CIPHER_P[j])
        prev = c[j]
    d = [0] * 5
    prev = CIPHER_SEED
    for j in range(4, -1, -1):
        d[j] = _md(c[j] + prev * CIPHER_P[4 - j] + CIPHER_K[4 - j])
        prev = d[j]
    return "".join(chr(97 + n) for n in d)


def main():
    if "--now" not in sys.argv:
        delay = random.uniform(0, WINDOW_MINUTES * 60)
        print(f"{datetime.now()}: sleeping {delay/60:.1f} min before fetching")
        time.sleep(delay)

    # NYT's Wordle "day" rolls over at midnight Eastern, not local time.
    eastern_date = datetime.now(ZoneInfo("America/New_York")).date()
    date_str = eastern_date.isoformat()

    url = f"https://www.nytimes.com/svc/wordle/v2/{date_str}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    solution = data["solution"].strip().lower()
    code = encrypt_word(solution)

    with open(OUTFILE, "w") as f:
        json.dump({"date": date_str, "code": code}, f)

    print(f"{datetime.now()}: wrote {date_str} -> {code}")

    subprocess.run(["git", "-C", REPO_DIR, "add", "daily.json"], check=True)
    # Anything staged? (exit code 1 = yes). If daily.json didn't change, skip the commit.
    staged = subprocess.run(["git", "-C", REPO_DIR, "diff", "--cached", "--quiet", "--", "daily.json"])
    if staged.returncode != 0:
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "commit", "-m", f"daily: {date_str}", "--", "daily.json"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("commit failed:", result.stdout, result.stderr)
            sys.exit(1)
    else:
        print("daily.json unchanged (already up to date for today)")

    # Push either way: harmless when there's nothing new, and it still checks the
    # GitHub login works, and sends any commit left over from an earlier failed push.
    subprocess.run(["git", "-C", REPO_DIR, "push"], check=True)
    print(f"{datetime.now()}: pushed.")


if __name__ == "__main__":
    main()
