"""Collect Bollnäs municipality calendar events into data/events.json.

Uses Python's standard library only. Never overwrites existing data if
source extraction fails. Times are local to Europe/Stockholm.
"""

import datetime as dt
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

SOURCE = "https://bollnas.se/evenemang"
OUTPUT = Path(__file__).resolve().parent / "data" / "events.json"
ZONE = ZoneInfo("Europe/Stockholm")
MONTHS = {name: number for number, name in enumerate(
    "januari februari mars april maj juni juli augusti september oktober november december".split(), 1
)}
CATEGORIES = [
    ("loppis", "Loppis"), ("bakluck", "Loppis"), ("auktion", "Auktion"),
    ("trav", "Trav"), ("bandy", "Bandy"),
    ("ishockey", "Hockey"), ("hockey", "Hockey"),
    ("marknad", "Marknad"), ("konsert", "Musik"),
    ("musik", "Musik"), ("sång", "Musik"),
    ("teater", "Kultur"), ("utställning", "Kultur"),
    ("konst", "Kultur"), ("bio", "Kultur"),
    ("film", "Kultur"), ("barn", "Familj"),
    ("skridsko", "Sport"), ("åkning", "Sport"),
    ("fotboll", "Sport"), ("idrott", "Sport"),
]
DATE_RE = re.compile(r"\bDen\s+(\d{1,2})\s+([a-zåäö]+)\s+(20\d{2})\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2})\b")


def clean(text):
    return " ".join(html.unescape(text or "").split())


class CalendarParser(HTMLParser):
    """Extract h2 event headings and the following list-item date/time/place."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = []
        self.current = None
        self.heading_depth = 0
        self.li_depth = 0
        self.li_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h2":
            self.current = {"title": "", "lines": [], "url": SOURCE}
            self.events.append(self.current)
            self.heading_depth += 1
        elif tag == "li" and self.current is not None:
            if self.li_depth == 0:
                self.li_parts = []
            self.li_depth += 1
        elif tag == "a" and self.heading_depth and self.current is not None:
            href = attrs.get("href", "")
            if href and not href.startswith(("#", "javascript:")):
                self.current["url"] = urljoin(SOURCE, href)

    def handle_data(self, data):
        if self.current is None:
            return
        if self.heading_depth:
            self.current["title"] += data
        if self.li_depth:
            self.li_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "h2":
            self.heading_depth = max(0, self.heading_depth - 1)
        elif tag == "li" and self.li_depth:
            self.li_depth -= 1
            if self.li_depth == 0 and self.current is not None:
                line = clean(" ".join(self.li_parts))
                if line:
                    self.current["lines"].append(line)


def classify(title):
    lower = title.casefold()
    # Public skating is a recreational activity, even when held in the bandy arena.
    if "allmänhetens åkning" in lower:
        return "Sport"
    if any(term in lower for term in (
        "kyrkokonsert", "kör", "big band", "bach", "sjung", "julkonsert",
        "christmas night", "mass of the children", "bön till solen",
        "schweitzer", "musikföreställning", "sinatra", "konsert"
    )):
        return "Musik"
    if any(term in lower for term in ("bingo", "företagarfrukost", "träffpunkt")):
        return "Övrigt"
    if any(term in lower for term in ("föreställning", "ebenezer", "teater")):
        return "Kultur"
    return next((category for term, category in CATEGORIES if term in lower), "Övrigt")


def location_from_title(title):
    """Return only a venue explicitly named in the event title."""
    lower = title.casefold()
    known = (
        ("sävstaås ip", "Sävstaås IP"),
        ("sbb arena", "SBB Arena"),
        ("mo kyrka", "Mo kyrka"),
        ("kulturhuset", "Kulturhuset Bollnäs"),
        ("bollnäs konsthall", "Bollnäs konsthall"),
        ("bollnästravet", "Bollnästravet"),
        ("kulturkvarteret", "Kulturkvarteret"),
        ("scandic", "Scandic"),
    )
    return next((place for phrase, place in known if phrase in lower), "")


def fetch(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; BollnasKalender/1.2)",
        "Accept": "text/html,application/xhtml+xml",
    })
    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read(5_000_000).decode("utf-8", "replace")


def parse_date(match):
    if not match:
        return None
    month = MONTHS.get(match.group(2).casefold())
    if month is None:
        return None
    try:
        return dt.date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def collect(page=None, today=None):
    if page is None:
        page = fetch(SOURCE)
    parser = CalendarParser()
    parser.feed(page)
    print(f"Fetched {len(page)} characters; found {len(parser.events)} headings.", flush=True)
    today = today or dt.datetime.now(ZONE).date()
    last_day = today + dt.timedelta(days=13)
    found = []

    for item in parser.events:
        title = clean(item["title"])
        if not title or len(title) > 180:
            continue
        date_line = next((line for line in item["lines"] if DATE_RE.search(line)), "")
        matches = list(DATE_RE.finditer(date_line))
        if not matches:
            continue
        start_day = parse_date(matches[0])
        end_day = parse_date(matches[1]) if len(matches) > 1 else start_day
        if not start_day or not end_day or end_day < start_day:
            continue
        time_line = next((line for line in item["lines"] if TIME_RE.search(line)), "")
        time_match = TIME_RE.search(time_line)
        if time_match:
            sh, sm, eh, em = (int(time_match.group(i)) for i in range(1, 5))
            if sh > 23 or eh > 23 or sm > 59 or em > 59:
                continue
            start_time = f"{sh:02}:{sm:02}"
            end_time = f"{eh:02}:{em:02}"
        else:
            start_time = "00:00"
            end_time = ""
        location = next((line for line in reversed(item["lines"])
                         if line != date_line and line != time_line
                         and not DATE_RE.search(line)), "")
        if not location:
            location = location_from_title(title)
        # A dated interval is shown once per day; never create dates outside source interval.
        first = max(today, start_day)
        last = min(last_day, end_day)
        for offset in range(max(0, (last - first).days + 1)):
            day = first + dt.timedelta(days=offset)
            found.append({
                "title": title,
                "start": f"{day.isoformat()}T{start_time}",
                "date": day.isoformat(),
                "time": start_time if time_match else "",
                "end": f"{day.isoformat()}T{end_time}" if end_time else "",
                "location": location,
                "category": classify(title),
                "url": item["url"],
                "source": SOURCE,
            })

    # Add verified home games from club fixture calendars. They are maintained
    # separately, so they can be checked against the official schedule.
    fixture_file = Path(__file__).resolve().parent / "data" / "sports_fixtures.json"
    if fixture_file.exists():
        sports = json.loads(fixture_file.read_text(encoding="utf-8")).get("fixtures", [])
        for game in sports:
            try:
                game_day = dt.date.fromisoformat(game["date"])
                start_time = game["time"]
                dt.time.fromisoformat(start_time)
            except (KeyError, ValueError, TypeError):
                continue
            if not today <= game_day <= last_day:
                continue
            # Prefer explicit club fixture over a less detailed municipality
            # listing for the same sport, day and home team.
            if game["category"] == "Bandy":
                found = [e for e in found if not (
                    e["date"] == game["date"] and e["category"] == "Bandy"
                    and ("bollnäs" in e["title"].casefold())
                )]
            found.append({
                "title": game["title"],
                "start": game["date"] + "T" + start_time,
                "date": game["date"],
                "time": start_time,
                "end": "",
                "location": game["location"],
                "category": game["category"],
                "url": game["url"],
                "source": game["url"],
            })

    unique = {(e["title"], e["start"], e["location"]): e for e in found}
    events = sorted(unique.values(), key=lambda e: (e["start"], e["title"]))
    print(f"Found {len(events)} dated events between {today} and {last_day}.", flush=True)
    if not events:
        raise RuntimeError("No events extracted. Refusing to overwrite events.json.")
    return events


def main():
    events = collect()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": dt.datetime.now(ZONE).isoformat(timespec="seconds"),
        "events": events,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(events)} events to {OUTPUT}", flush=True)


if __name__ == "__main__":
    main()
