"""Collect verified Bollnäs municipality events for the next 14 days.
Uses only the Python standard library. Never replaces good data with an empty list.
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
SOURCE = 'https://bollnas.se/evenemang'
OUTPUT = Path(__file__).resolve().parent / 'data' / 'events.json'
MONTHS = {name: i for i, name in enumerate('januari februari mars april maj juni juli augusti september oktober november december'.split(), 1)}
CATEGORIES = [('loppis','Loppis'), ('bakluck','Loppis'), ('auktion','Auktion'),
('trav','Trav'), ('bandy','Bandy'), ('ishockey','Hockey'),
('hockey','Hockey'), ('marknad','Marknad'), ('konsert','Musik'),
('musik','Musik'), ('teater','Kultur'), ('utställning','Kultur'),
('bio','Kultur'), ('film','Kultur'), ('barn','Familj')]
DATE_RE = re.compile(r'\bDen\s+(\d{1,2})\s+([a-zåäö]+)\s+(20\d{2})\b', re.I)
TIME_RE = re.compile(r'\b(\d{1,2}):(\d{2})\s*[—–-]\s*(\d{1,2}):(\d{2})\b')
def clean(text):
return ' '.join(html.unescape(text or '').split())
class CalendarParser(HTMLParser):
"""Read the municipality's event headings and their following list of details."""
def __init__(self):
super().__init__(convert_charrefs=True)
self.events = []
self.current = None
self.heading_depth = 0
self.li_depth = 0
self.li_parts = []
self.in_heading = False
def handle_starttag(self, tag, attrs):
attrs = dict(attrs)
if tag == 'h2':
self.current = {'title': '', 'lines': [], 'url': SOURCE}
self.events.append(self.current)
self.in_heading = True
elif tag == 'li' and self.current is not None:
if self.li_depth == 0:
self.li_parts = []
self.li_depth += 1
elif tag == 'a' and self.current is not None and self.in_heading:
href = attrs.get('href', '')
if href and not href.startswith(('#', 'javascript:')):
self.current['url'] = urljoin(SOURCE, href)
def handle_data(self, data):
if self.current is None:
return
if self.in_heading:
self.current['title'] += data
if self.li_depth:
self.li_parts.append(data)
def handle_endtag(self, tag):
if tag == 'h2':
self.in_heading = False
elif tag == 'li' and self.li_depth:
self.li_depth -= 1
if self.li_depth == 0 and self.current is not None:
line = clean(' '.join(self.li_parts))
if line:
self.current['lines'].append(line)
def classify(title):
lower = title.casefold()
return next((category for term, category in CATEGORIES if term in lower), 'Övrigt')
def fetch(url):
req = urllib.request.Request(url, headers={
'User-Agent': 'Mozilla/5.0 (compatible; BollnasKalender/1.1; event index)',
'Accept': 'text/html,application/xhtml+xml',
})
with urllib.request.urlopen(req, timeout=30) as response:
return response.read(5_000_000).decode('utf-8', 'replace')
def collect():
page = fetch(SOURCE)
parser = CalendarParser()
parser.feed(page)
print(f'Fetched {len(page)} characters; found {len(parser.events)} headings.', flush=True)
today = dt.datetime.now(ZoneInfo('Europe/Stockholm')).date()
last_day = today + dt.timedelta(days=13)
found = []
for item in parser.events:
title = clean(item['title'])
if not title or len(title) > 180:
continue
date_line = next((line for line in item['lines'] if DATE_RE.search(line)), '')
match = DATE_RE.search(date_line)
if not match:
continue
month = MONTHS.get(match.group(2).lower())
if not month:
continue
try:
day = dt.date(int(match.group(3)), month, int(match.group(1)))
except ValueError:
continue
if not today <= day <= last_day:
continue
time_line = next((line for line in item['lines'] if TIME_RE.search(line)), '')
time_match = TIME_RE.search(time_line)
start_time = f'{int(time_match.group(1)):02d}:{time_match.group(2)}' if time_match else '00:00'
end_time = f'{int(time_match.group(3)):02d}:{time_match.group(4)}' if time_match else ''
location = next((line for line in reversed(item['lines'])
if line != date_line and line != time_line and not DATE_RE.search(line)), '')
found.append({
'title': title,
'start': f'{day.isoformat()}T{start_time}',
'date': day.isoformat(),
'time': start_time if time_match else '',
'end': f'{day.isoformat()}T{end_time}' if end_time else '',
'location': location,
'category': classify(title),
'url': item['url'],
'source': SOURCE,
})
unique = {(e['title'], e['start'], e['location']): e for e in found}
events = sorted(unique.values(), key=lambda e: (e['start'], e['title']))
print(f'Found {len(events)} dated events between {today} and {last_day}.', flush=True)
if not events:
raise RuntimeError('No events extracted. Refusing to overwrite events.json; inspect source
markup.')
return events
def main():
events = collect()
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
payload = {
'updated': dt.datetime.now(ZoneInfo('Europe/Stockholm')).isoformat(timespec='seconds'),
'events': events,
}
OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Saved {len(events)} events to {OUTPUT}', flush=True)
