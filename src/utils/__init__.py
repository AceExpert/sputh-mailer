import string, random, re, subprocess

from models import DnsRecord
from utils.timers import interval, timeout

def gen_token(length: int = 10) -> str:

    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def get_dns_record(domain: str, record: str) -> list[DnsRecord]:
    res = re.findall(
        r';; ANSWER SECTION\:\n(.+?)\n;', 
        subprocess.check_output(['dig', domain, record]).decode(), 
        re.DOTALL
    )
    if res:
        records: list[list[str]] = [[]]
        for chr in res[0]:
            if chr not in ['\t', ' ', '\n']:
                if not len(records[-1]):
                    records[-1].append(chr)
                else:
                    records[-1][-1] += chr
            elif chr == '\n':
                if len(records[-1]):
                    records.append([])
            else:
                if len(records[-1]) and len(records[-1][-1]):
                    records[-1].append('')
        if len(records) and not len(records[-1]):
            records.pop()
        return [*map(
            lambda rec: DnsRecord(
                            host = rec[0], 
                            value = rec[-1], 
                            label = rec[3], 
                            ttl = int(rec[1]), 
                            priority = rec[-2] if rec[3] == 'MX' else -1
                        ), records
        )]
    else:
        return []
    
def get_email(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9\$%\-#&\.]+@(?:[a-zA-Z0-9\-]+\.)*[a-zA-Z0-9\-]+\.(?:[a-zA-Z0-9\-]+\.)?[a-zA-Z0-9\-]+", text)