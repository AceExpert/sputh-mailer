import string, random, re, subprocess

from models import DnsRecord
from utils.timers import interval, timeout

email_pattern: str = r"[a-zA-Z0-9\$%\-#&\.]+@(?:[a-zA-Z0-9\-]+\.)*[a-zA-Z0-9\-]+\.(?:[a-zA-Z0-9\-]+\.)?[a-zA-Z0-9\-]+"
email_list_pat: str = r'(?:[^\s]*' + email_pattern + r'[^\s]*\s*,?\s*)*'

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
                            priority = int(rec[-2]) if rec[3] == 'MX' else -1
                        ), records
        )]
    else:
        return []

def get_email(text: str) -> list[str]:
    return re.findall(email_pattern, text)

def get_folder_path(user: str, folder: str) -> str:
    return re.findall(r"(.+)(?:[/\\].+){3}", __file__)[0] + f'/drive/{user}/emails/{folder}/{folder}.db'

def get_name_from_header(txt: str) -> str:
    return re.sub(email_list_pat, '', txt).strip()