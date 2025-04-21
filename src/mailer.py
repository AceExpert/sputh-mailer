#!/usr/bin/python3 main.py
import smtplib
import sys
import enum

from db import EmailManager
from mailcomposer import MailComposer
from utils import get_email, get_dns_record

class State(enum.Enum):
    start = 0
    value = 1

opts = ['--to', '-t', '--from', '-f', '--name', '-n', '--message', '-m', '--subject', '-s', '--domain', '-d']

args = sys.argv

state = State.start
opt = None

data = {
    'to': [],
    'from': '',
    'domain': 'sayutel.com',
    'message': '',
    'subject': '',
}

for arg in args:
    if state == State.start:
        if arg in opts:
            state = State.value
            opt = arg
    else:
        if opt == '--to' or opt == '-t':
            for em in get_email(arg):
                data['to'].append(em)
        elif opt == '--from' or opt == '-f':
            if em := get_email(arg):
                data['from'] = em[0]
            else:
                print("Invalid from address")
                exit(1)
        elif opt == '--message' or opt == '-m':
            data['message'] = arg
        elif opt == '--subject' or opt == '-s':
            data['subject'] = arg
        elif opt == '--domain' or opt == '-d':
            data['domain'] = arg
        elif opt == '--name' or opt == '-n':
            data['name'] = arg
        state = State.start

user = data['from'].split('@')[0]

db = EmailManager(user)
composer = MailComposer(data.get('name', user), user, data['domain'], ', '.join(data['to']), subject = data['subject'])

composer.set_content(data['message'])
composer.set_html(data['message'])

segmented_mails = {}

for em in data['to']:
    domain = em.split('@')[1]
    segmented_mails.setdefault(domain, [])
    segmented_mails[domain].append(em)

for domain, emails in segmented_mails.items():
    records = get_dns_record(domain, 'MX')
    print(min(records, key = lambda rec: rec.priority).value[:-1])
    client = smtplib.SMTP_SSL(min(records, key = lambda rec: rec.priority).value[:-1], local_hostname='sayutel.com')
    client.sendmail(data['from'], emails, composer.get_bytes())