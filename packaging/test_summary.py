"""Publish readable test outcomes in the public Actions summary, not raw logs."""
import os
from pathlib import Path
import xml.etree.ElementTree as ET

report = Path('test-results.xml')
summary = Path(os.environ['GITHUB_STEP_SUMMARY'])
with summary.open('a', encoding='utf-8') as out:
    out.write('## Test results\n\n')
    if report.exists():
        root = ET.parse(report).getroot()
        for suite in root.iter('testsuite'):
            out.write(f"Tests: {suite.get('tests')}; failures: {suite.get('failures')}; errors: {suite.get('errors')}; skipped: {suite.get('skipped')}\n\n")
        for case in root.iter('testcase'):
            for failure in list(case.findall('failure')) + list(case.findall('error')):
                out.write(f"### {case.get('classname')}.{case.get('name')}\n\n```text\n{(failure.text or '')[:16000]}\n```\n\n")
    else:
        out.write('No JUnit report generated. Inspect installation/collection logs.\n')
