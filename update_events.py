"""Bollnäs Kalender: conservative municipal calendar HTML + JSON-LD collector.
No fabricated events. The municipality may change its markup or paginate results.
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
MONTHS = {'januari':1,'februari':2,'mars':3,'april':4,'maj':5,'juni':6,'juli':7,'augusti':8,'september':9,'oktober':10,'november':11,'december':12}
CATS = [('loppis','Loppis'),('bakluck','Loppis'),('auktion','Auktion'),('trav','Trav'),('bandy','Bandy'),('hockey','Hockey'),('ishockey','Hockey'),('marknad','Marknad'),('konsert','Musik'),('musik','Musik'),('teater','Kultur'),('utställning','Kultur'),('bio','Kultur'),('film','Kultur'),('barn','Familj')]

class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading = False
        self.li_depth = 0
        self.script = False
        self.script_parts = []
        self.json_scripts = []
        self.events = []
        self.current = None
        self.li_parts = []
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('type','').lower() == 'application/ld+json':
            self.script = True; self.script_parts = []
        if tag == 'h2':
            self.heading = True
            self.current = {'title':'','lines':[], 'url':SOURCE}
            self.events.append(self.current)
        if tag == 'li' and self.current:
            self.li_depth += 1
            if self.li_depth == 1: self.li_parts = []
        if tag == 'a' and self.current and attrs.get('href') and self.current['url'] == SOURCE:
            href = attrs['href']
            if href.startswith('/') and 'evenemang' in href:
                self.current['url'] = urljoin(SOURCE, href)
    def handle_data(self, data):
        if self.script: self.script_parts.append(data)
        if self.heading and self.current: self.current['title'] += data
        if self.li_depth and self.current: self.li_parts.append(data)
    def handle_endtag(self, tag):
        if tag == 'script' and self.script:
            self.json_scripts.append(''.join(self.script_parts)); self.script = False
        if tag == 'h2': self.heading = False
        if tag == 'li' and self.li_depth:
            self.li_depth -= 1
            if self.li_depth == 0 and self.current:
                line = ' '.join(''.join(self.li_parts).split())
                if line: self.current['lines'].append(line)

def json_events(node):
    if isinstance(node, list):
        for child in node: yield from json_events(child)
    elif isinstance(node, dict):
        kinds = node.get('@type', [])
        if isinstance(kinds, str): kinds = [kinds]
        if 'Event' in kinds: yield node
        for field in ('@graph','itemListElement'):
            yield from json_events(node.get(field, []))

def classify(title):
    lower = title.casefold()
    return next((category for term,category in CATS if term in lower), 'Övrigt')

def clean(value):
    return ' '.join(html.unescape(value or '').split())

def collect():
    req = urllib.request.Request(SOURCE, headers={'User-Agent':'Mozilla/5.0 (compatible; BollnasKalender/1.0; community event index)'})
    with urllib.request.urlopen(req, timeout=25) as response:
        page = response.read(5_000_000).decode('utf-8','replace')
    parser = CalendarParser(); parser.feed(page)
    found = []
    for item in parser.events:
        title = clean(item['title'])
        if not title or len(title) > 180: continue
        lines = item['lines']
        date_line = next((line for line in lines if re.search(r'\bDen\s+\d{1,2}\s+[a-zåäö]+\s+20\d\d',line,re.I)), None)
        if not date_line: continue
        match = re.search(r'\bDen\s+(\d{1,2})\s+([a-zåäö]+)\s+(20\d\d)', date_line, re.I)
        if not match: continue
        month = MONTHS.get(match.group(2).lower())
        if not month: continue
        try: day = dt.date(int(match.group(3)), month, int(match.group(1)))
        except ValueError: continue
        time_line = next((line for line in lines if re.search(r'\b\d\d?:\d\d\s*[—–-]\s*\d\d?:\d\d',line)), '')
        time_match = re.search(r'(\d{1,2}:\d\d)',time_line)
        start = day.isoformat() + ('T' + time_match.group(1).zfill(5) if time_match else 'T00:00')
        location = next((line for line in reversed(lines) if line != date_line and line != time_line and not line.lower().startswith('den ')), '')
