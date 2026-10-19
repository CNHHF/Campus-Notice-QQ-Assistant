import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class BootstrapTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows PowerShell regression')
    def test_startup_reads_utf8_chinese_configuration(self):
        script=(Path(__file__).resolve().parents[1]/'start-services.ps1').read_text(encoding='utf-8')
        begin=script.index('Get-Content -LiteralPath $cfgPath')
        end=script.index(').bot_qq',begin)
        expression=script[begin:end]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            path.write_text(json.dumps({'bot_qq':'12345678','groups':[{'label':'通知测试群'}]},ensure_ascii=False),encoding='utf-8')
            command="$ErrorActionPreference='Stop';$cfgPath='"+str(path).replace("'","''")+"';Write-Output (("+expression+").bot_qq)"
            encoded=base64.b64encode(command.encode('utf-16le')).decode()
            result=subprocess.run(['powershell.exe','-NoProfile','-EncodedCommand',encoded],capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,'UTF-8 startup configuration parsing failed')
            self.assertEqual(result.stdout.decode().strip(),'12345678')
