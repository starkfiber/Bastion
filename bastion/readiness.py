"""Local capability probes; availability is never reported as integration qualification."""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile


def inspect():
    result={'schema':'bastion.readiness.v1','hostTools':{name:shutil.which(name) for name in ('codex','docker','podman','limactl')},
        'livePlannerQualified':False,'schedulerInstalledByBastion':False,'checkWorkerEnforcesOSIsolation':False,
        'notes':['Presence is not execution qualification.','No provider connection, host installation or private-file inspection is performed.']}
    executable=Path('/usr/bin/sandbox-exec')
    if not executable.is_file():
        result['isolationProbe']={'passed':False,'status':'unavailable','boundariesMeasured':False}
        return result
    with tempfile.TemporaryDirectory(prefix='bastion-isolation-probe-') as temp, socket.socket() as listener:
        root=Path(temp).resolve(); inside=root/'allowed'; inside.mkdir()
        outside=root/'outside.txt'; outside.write_text('synthetic boundary sentinel')
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        literals=' '.join('(subpath '+json.dumps(p)+')' for p in ['/System','/usr','/Library/Developer','/Library/Apple','/private/var/db/dyld',str(inside)])
        profile='(version 1)(deny default)(allow process*)(allow file-read* '+literals+' (literal "/dev/null") (literal "/dev/urandom"))(allow file-write* (subpath '+json.dumps(str(inside))+'))(deny network*)'
        script='''import json,socket
from pathlib import Path
r={}
for label,fn in [('outsideReadDenied',lambda:Path(OUTSIDE).read_text()),('outsideWriteDenied',lambda:Path(OUTSIDE).write_text('changed')),('networkDenied',lambda:socket.create_connection(('127.0.0.1',PORT),timeout=1))]:
 try:
  value=fn()
  if label=='networkDenied': value.close()
  r[label]=False
 except PermissionError: r[label]=True
 except OSError: r[label]=False
try:
 Path(INSIDE).write_text('allowed')
 r['allowedWriteSucceeded']=True
except OSError: r['allowedWriteSucceeded']=False
print(json.dumps(r))
'''.replace('OUTSIDE',repr(str(outside))).replace('INSIDE',repr(str(inside/'ok.txt'))).replace('PORT',str(listener.getsockname()[1]))
        try:
            child=subprocess.run([str(executable),'-p',profile,sys.executable,'-I','-B','-c',script],capture_output=True,text=True,timeout=5)
            measured=json.loads(child.stdout) if child.returncode==0 else None
            passed=bool(measured and all(measured.get(k) is True for k in ('outsideReadDenied','outsideWriteDenied','networkDenied','allowedWriteSucceeded')))
            result['isolationProbe']={'passed':passed,'exitCode':child.returncode,'boundariesMeasured':measured is not None,
                'observations':measured,'diagnostic':child.stderr[:1000],
                'scope':'disposable synthetic sentinel and loopback listener only; not a qualified check-worker backend'}
        except (OSError,ValueError,subprocess.TimeoutExpired) as exc:
            result['isolationProbe']={'passed':False,'status':'probe-unavailable','boundariesMeasured':False,'diagnostic':str(exc)}
    return result
