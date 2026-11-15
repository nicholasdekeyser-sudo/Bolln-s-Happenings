"""Refresh home games from Bollnäs GIF bandy and Bollnäs IS hockey daily.
If a source cannot be parsed, preserve previously verified fixtures.
"""
import datetime as dt
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

OUTPUT = Path(__file__).resolve().parent / "data" / "sports_fixtures.json"
BANDY = "https://www.bollnasbandy.se/herrmatcher"
HOCKEY = "https://www.bollnashockey.se/bollnasis-a-lag/matcher"
MONTHS = dict(zip("januari februari mars april maj juni juli augusti september oktober november december".split(), range(1, 13)))
SHORT = dict(zip("jan feb mar apr maj jun jul aug sep okt nov dec".split(), range(1, 13)))
DAY = r"(?:mån|tis|ons|tor|fre|lör|sön)"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "svg"):
            self.hidden.append(tag)
        elif not self.hidden and tag in ("br", "p", "div", "section", "li", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in ("p", "div", "section", "li", "h1", "h2", "h3"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data + " ")

    def text(self):
        return re.sub(r"\s+", " ", "".join(self.parts)).strip()


def fetch(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BollnasKalender/1.3)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(request, timeout=35) as response:
        page = response.read(6_000_000).decode("utf-8", "replace")
    parser = VisibleText()
    parser.feed(page)
    return parser.text()


def fixture(day, time, opponent, category):
    bandy = category == "Bandy"
    return {
        "date": day.isoformat(),
        "time": time,
        "title": f'{category}: {"Bollnäs GIF" if bandy else "Bollnäs IS"} – {opponent}',
        "location": "SBB Arena" if bandy else "Bollnäs Ishall",
        "category": category,
        "url": BANDY if bandy else HOCKEY,
    }


def parse_bandy(text, season):
    header = re.compile(r"\b(Hemma|Borta)\s+" + DAY + r"\s+(\d{1,2})\s+(jan|feb|mar|apr|maj|jun|jul|aug|sep|okt|nov|dec)\s+(\d{1,2}:\d{2})\b", re.I)
    rows = list(header.finditer(text))
    if len(rows) < 3:
        raise ValueError("Bandy match list not recognized")
    matches = []
    for i, row in enumerate(rows):
        if row.group(1).lower() != "hemma":
            continue
        end = rows[i + 1].start() if i + 1 < len(rows) else row.end() + 300
        body = text[row.end():end]
        opponent_match = re.search(r"Bollnäs GOIF BF\s+(.*?)\s+SBB Arena\b", body, re.I)
        if not opponent_match:
            continue
        opponent = re.sub(r"^\d+\s+", "", opponent_match.group(1))
        opponent = re.sub(r"\s+\d+$", "", opponent).strip(" -–")
        if not opponent or len(opponent) > 90:
            continue
        month = SHORT[row.group(3).lower()]
        year = season if month >= 7 else season + 1
        try:
            day = dt.date(year, month, int(row.group(2)))
            dt.time.fromisoformat(row.group(4))
        except ValueError:
            continue
        matches.append(fixture(day, row.group(4), opponent, "Bandy"))
    if not matches:
        raise ValueError("No home bandy matches parsed")
    return matches


def parse_hockey(text, season):
    sections = list(re.finditer(r"\b(" + "|".join(MONTHS) + r")\b(?:\s*-\s*(20\d{2}))?", text, re.I))
    if len(sections) < 3 or "Bollnäs Ishockeysällskap" not in text:
        raise ValueError("Hockey match list not recognized")
    match = re.compile(r"\b" + DAY + r"\s+(\d{1,2})\s+(\d{1,2}:\d{2})\s+(?:\d+\s*[-–]\s*\d+\s*(?:ES|EF)?\s*|[-–]\s*)?Bollnäs Ishockeysällskap\s*[-–]\s*(.*?)\s+Bollnäs Ishall\b", re.I)
    games = []
    for i, section in enumerate(sections):
        end = sections[i + 1].start() if i + 1 < len(sections) else len(text)
        month = MONTHS[section.group(1).lower()]
        year = int(section.group(2)) if section.group(2) else (season if month >= 7 else season + 1)
        for row in match.finditer(text[section.end():end]):
            opponent = row.group(3).strip()
            if not opponent or len(opponent) > 85:
                continue
            try:
                day = dt.date(year, month, int(row.group(1)))
                dt.time.fromisoformat(row.group(2))
            except ValueError:
                continue
            games.append(fixture(day, row.group(2), opponent, "Hockey"))
    if not games:
        raise ValueError("No home hockey matches parsed")
    return games


def update(previous, today, loader=fetch):
    season = today.year if today.month >= 7 else today.year - 1
    kept = [e for e in previous if e.get("category") not in ("Bandy", "Hockey")]
    refreshed = 0
    for category, url, parser in (("Bandy", BANDY, parse_bandy), ("Hockey", HOCKEY, parse_hockey)):
        old = [e for e in previous if e.get("category") == category]
        try:
            games = parser(loader(url), season)
            future = [g for g in games if g["date"] >= today.isoformat()]
            if not future and today.month not in (3, 4, 5, 6):
                raise ValueError("No future matches found; keeping old data")
            kept.extend(future)
            refreshed += 1
            print(f"{category}: updated {len(future)} upcoming home games", flush=True)
        except (OSError, ValueError, UnicodeError) as error:
            kept.extend(e for e in old if e.get("date", "") >= today.isoformat())
            print(f"WARNING: {category} not refreshed ({error}); retained previous fixtures", flush=True)
    unique = {(e["category"], e["date"], e["title"]): e for e in kept}
    return sorted(unique.values(), key=lambda e: (e["date"], e["time"], e["title"])), refreshed


def main():
    now = dt.datetime.now(ZoneInfo("Europe/Stockholm"))
    previous = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {"fixtures": []}
    fixtures, refreshed = update(previous.get("fixtures", []), now.date())
    if not fixtures and not refreshed:
        raise RuntimeError("Both clubs unavailable and no cached fixtures")
    payload = {
        "note": "Club home fixtures checked daily. Consult club for last-minute changes.",
        "updated": now.isoformat(timespec="seconds"),
        "fixtures": fixtures,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(fixtures)} fixtures; refreshed {refreshed} sources", flush=True)


if __name__ == "__main__":
    main()
