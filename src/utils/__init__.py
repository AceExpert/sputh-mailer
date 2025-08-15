import string, random, re, subprocess, sqlite3, os

from models import DnsRecord
from utils.timers import interval, timeout

email_pattern: str = r"[a-zA-Z0-9\$%\-#&\.]+@(?:[a-zA-Z0-9\-]+\.)*[a-zA-Z0-9\-]+\.(?:[a-zA-Z0-9\-]+\.)?[a-zA-Z0-9\-]+"
email_list_pat: str = r'(?:[^\s]*' + email_pattern + r'[^\s]*\s*,?\s*)*'

auth_dir: str = r''

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
    parts = user.lower().split('@', 1)
    user_id = None
    domain = None

    if len(parts) == 2:
        user_id, domain = parts
    else:
        user_id = parts[0]
        domain = 'sputh.me'

    get_path = lambda dom: re.findall(r"(.+)(?:[/\\].+){3}", __file__)[0] + f'/drive/{dom}/{user_id}/emails/{folder}/{folder}.db'
    get_dom_folder_path = lambda dom: re.findall(r"(.+)(?:[/\\].+){3}", __file__)[0] + f'/drive/{dom}'
    
    if os.path.exists(get_dom_folder_path(domain)):
        return get_path(domain)
    else:
        db = sqlite3.connect(auth_dir + '/users.db')
        cursor = db.cursor()
        for info in cursor.execute('SELECT user_id, domain, dom_alias FROM users WHERE user_id=?', (user_id,)).fetchall():
            if domain in info[2].split(','):
                db.close()
                return get_path(info[1])

def get_name_from_header(txt: str) -> str:
    return re.sub(email_list_pat, '', txt).strip()