"""Conservative collector: only published structured Event JSON-LD from allowlisted sites.
Does not claim full municipal coverage. No invented events."""
import json, re, datetime, urllib.request, html.parser
from pathlib import Path
SOURCES=["https://bollnas.se/evenemang"]
CATEGORIES={"trav":"Trav","bandy":"Bandy","hockey":"Hockey","loppis":"Loppis","auktion":"Auktion","marknad":"Marknad","konsert":"Musik","teater":"Kultur"}
class Scripts(html.parser.HTMLParser):
 def __init__(self): super().__init__();self.active=False;self.parts=[];self.items=[]
 def handle_starttag(self,tag,attrs):
  if tag=='script' and dict(attrs).get('type','').lower()=='application/ld+json':self.active=True;self.parts=[]
 def handle_data(self,data):
  if self.active:self.parts.append(data)
 def handle_endtag(self,tag):
  if tag=='script' and self.active:self.items.append(''.join(self.parts));self.active=False

def nodes(x):
 if isinstance(x,list):
  for v in x:yield from nodes(v)
 elif isinstance(x,dict):
  if x.get('@type')=='Event' or (isinstance(x.get('@type'),list) and 'Event' in x['@type']):yield x
  for k in ('@graph','itemListElement'):yield from nodes(x.get(k,[]))

def main():
 today=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=1))).date();end=today+datetime.timedelta(days=14);out=[]
 for url in SOURCES:
  try:
   req=urllib.request.Request(url,headers={'User-Agent':'BollnasKalender/1.0 (public community calendar)'})
   with urllib.request.urlopen(req,timeout=15) as r:page=r.read(2000000).decode('utf-8','replace')
   parser=Scripts();parser.feed(page)
   for script in parser.items:
    try:structured=json.loads(script)
    except ValueError:continue
    for event in nodes(structured):
     start=event.get('startDate','');name=event.get('name','');link=event.get('url','')
     if not all(isinstance(v,str) and v for v in (start,name,link)):continue
     try:day=datetime.date.fromisoformat(start[:10])
     except ValueError:continue
     if not today<=day<end:continue
     loc=event.get('location',{});loc=loc.get('name','') if isinstance(loc,dict) else ''
     category=next((v for k,v in CATEGORIES.items() if k in name.lower()),'Övrigt')
     out.append({'title':name,'start':start,'location':loc,'category':category,'url':link})
  except Exception as e:print('Source unavailable:',url,str(e))
 seen=set();unique=[]
 for e in out:
  key=(e['title'].casefold(),e['start'][:10]);
  if key not in seen:seen.add(key);unique.append(e)
 path=Path('data/events.json');previous=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'events':[]}
 # Preserve still-upcoming known events on transient source failures, but never fabricate.
 for e in previous.get('events',[]):
  try:valid=today<=datetime.date.fromisoformat(e['start'][:10])<end
  except (ValueError,KeyError,TypeError):valid=False
  if valid and (e.get('title','').casefold(),e['start'][:10]) not in seen:unique.append(e)
 path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'updated':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='minutes'),'events':unique},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print('Events:',len(unique))
if __name__=='__main__':main()
