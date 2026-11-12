import sys, json, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from main import create_app,db
temp_dir=tempfile.TemporaryDirectory(prefix='vi-uni-ui-test-')
app=create_app({'TESTING':True,'SECRET_KEY':'dom-integration-only','SQLALCHEMY_DATABASE_URI':'sqlite:///' + str(Path(temp_dir.name)/'ui-test.db')})
with app.app_context():
 db.drop_all();db.create_all()
c=app.test_client()
print(json.dumps({'html':c.get('/').text}),flush=True)
for line in sys.stdin:
 try:
  p=json.loads(line)
  kwargs={'method':p.get('method','GET'),'headers':p.get('headers',{})}
  if p.get('body'):kwargs['data']=p['body']
  r=c.open(p['path'],**kwargs)
  print(json.dumps({'id':p['id'],'ok':r.status_code<400,'status':r.status_code,'data':r.json}),flush=True)
 except Exception as e:
  print(json.dumps({'id':p['id'],'error':str(e)}),flush=True)

temp_dir.cleanup()
