import json
import smtplib
import ssl
import sqlite3

import ws

from typing import Any
from threading import Thread

from db import EmailManager, SimpleEmail
from crypt import ECC, private_key
from models import Channel, DnsRecord, Interval
from utils import gen_token, get_dns_record, get_email
from mailcomposer import MailComposer

from server import SayutelMailServer, SMTPClientInfo

ws.Message.client = property(lambda self: self.author)

sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
sslctx.load_cert_chain('/etc/letsencrypt/archive/sayutel.com/fullchain1.pem', '/etc/letsencrypt/archive/sayutel.com/privkey1.pem')

class AccessDB:

    def __init__(self):
        self.db = sqlite3.connect('/home/db/sputhmail/access.db')
        self.cursor = self.db.cursor()

    def get_user(self, token: str):
        user = self.cursor.execute("SELECT user from users WHERE token=?;", (token,)).fetchone()
        if user:
            return user[0]

class SputhMailer(ws.ServerSocket):

    def __init__(self):
        super().__init__()
        self.open_channels: dict[Any, Channel] = {}
        self.smtp_client: smtplib.SMTP = None
        self.ecc = ECC()
        self.access_db = AccessDB()
        self.mailserver = SayutelMailServer(None)
        self.mailserver.add_listener(self.on_mail)

    async def on_mail(self, info: SMTPClientInfo, data: tuple, folder: str = None, category: str = None):
        # print('Received from:', info.ehlo_domain)
        # print('Return-Path:', info.mail_from)
        # print('RCPT TO:', info.rcpt_to)
        # print('Encrypted:', info.is_tls)
        # print()
        # print(data)
        for user in info.rcpt_to:
            for chans in self.open_channels.values():
                if chans.user == user.lower():
                    await self.send_msg(chans.client, {'folder': folder or 'inbox', 'event': 1, 'mail': SimpleEmail.from_mail(data)}, chans.pub_key)

    async def on_ready(self):
        print("Server listening @ 0.0.0.0:3008")

    async def on_connect(self, client, path):
        print("Client connected @", client.remote_address)
        hbtimeout = Interval(150, self.end_connection, (client,), once_only = True)
        hbinterval = Interval(120, self.send_hb, (client,))
        self.open_channels[client.remote_address] = Channel(
            client = client,
            session_token = gen_token(), 
            auth = False,
            stale_timer = hbtimeout,
            hb_timer = hbinterval,
        )
        hbinterval.start(self.loop)
        hbtimeout.start(self.loop)

    async def on_message(self, message):
        if message.client.remote_address in self.open_channels:
            self.loop.create_task(self.on_client_message(self.open_channels[message.client.remote_address], message))

    async def on_client_message(self, channel: Channel, message):
        #print(message)
        channel.stale_timer.restart()
        data = message.data
        key = channel.current_key or private_key

        if isinstance(data, dict):

            if 'en' in data:
                fdata = ws.Object(json.loads(self.ecc.decrypt(data.en, key)))
                print(fdata)
                if 'action' in fdata:
                    
                    if fdata.action == 0:
                        channel.pub_key = bytes(bytearray(fdata.key))
                        (channel.current_key, client_pub_key) = self.ecc.generate_keys()
                        await channel.client.send(data = {'chan': self.ecc.encrypt_s1(json.dumps([*client_pub_key]))})

                    elif fdata.action == 1:
                        await self.auth_req(channel, fdata)

                    elif fdata.action == 2:
                        await self.send_mail(channel, fdata['data'])

                    elif fdata.action == 3:
                        await self.fetch_mails(channel, fdata['data'])

                    elif fdata.action == -1:
                        await self.sign_up(channel, fdata['data'])
        else:
            
            if data == 're':
                channel.current_key = None

    async def auth_req(self, channel: Channel, data: dict):
        if user := self.access_db.get_user(data.token):
            channel.auth = True
            channel.user = user
            channel.info = ws.Object({
                'user': user.split('@')[0],
                'name': user.split('@')[0].title(),
            })
            channel.manager = EmailManager(data.user)
            await self.send_msg(channel.client, {'auth': 1}, channel.pub_key)
        else:
            await self.send_msg(channel.client, {'auth': 0}, channel.pub_key)

    async def fetch_mails(self, channel: Channel, data: dict):
        folder: str = data.folder
        category = data.get('category', 'all')
        mails = channel.manager.get_mails(folder, data.get('limit', 50), data.get('offset', 0))
        await self.send_msg(channel.client, {'folder': folder, 'category': category, 'mails': mails, 'count': len(mails), 'start': mails[-1]['index'] if len(mails) else -1, 'fetch_id': data.get('id', None), 'offset': data.get('offset', 0)}, channel.pub_key)

    async def send_mail(self, channel: Channel, data: dict):
        #from_address = get_email(data['from'])
        from_dom = data['fromDomain'][0]
        to_address = get_email(data['toAddr'])[0]
        mail = MailComposer(channel.info.name, channel.info.user, from_dom, to = to_address, subject = data.get("subject", None), content = data.get('content', None))
        mail.set_html(data['html'] if 'html' in data and data.get('html', None) else data.get('content', None))
        mail.sign(data['sign'][0], 'dragon')
        self.records: list[DnsRecord] = get_dns_record(to_address.split("@")[1], "MX")
        if not self.records:
            return await self.send_msg(channel.client, {'error': 1, 'msg': "domain does not accept emails", 'resp': data.get('id', None)}, channel.pub_key)
        try:
            self.smtp_client = smtplib.SMTP(min(self.records, key = lambda rec: rec.priority).value[:-1], local_hostname = from_dom)
            #self.smtp_client.starttls()
            self.smtp_client.sendmail(f'{channel.info.user}@{from_dom}', to_address, mail.get_bytes())
            self.smtp_client.quit()
            channel.manager.add_mail('sent', mail.message, f'{channel.info.user}@{from_dom}', to_address)
            await self.send_msg(channel.client, {'error': 0, 'msg': "success", 'resp': data.get('id', None)}, channel.pub_key)
        except smtplib.SMTPResponseException as e:
            await self.send_msg(channel.client, {'error': 2, 'code': e.smtp_code, 'msg': e.smtp_error, 'resp': data.get('id', None)}, channel.pub_key)
        except smtplib.SMTPException as e:
            await self.send_msg(channel.client, {'error': 6, 'msg': e.strerror, 'resp': data.get('id', None)}, channel.pub_key)

    async def sign_up(channel, fdata):
        pass

    async def send_msg(self, client, data, key):
        await client.send(data = {'en': self.ecc.encrypt(json.dumps(data), key)})

    async def on_disconnect(self, client, code, reason):
        await self.end_connection(client)

    async def on_close(self, client, code, reason):
        await self.end_connection(client)

    async def send_hb(self, client):
        await client.send(content = ".")

    async def end_connection(self, client):
        try:
            await client.close()
        except Exception:
            pass

        try:
            self.open_channels[client.remote_address].stale_timer.stop()
            self.open_channels[client.remote_address].hb_timer.stop()
            del self.open_channels[client.remote_address]
        except Exception:
            pass

server = SputhMailer()

def startMailServer():
    server.mailserver.loop.run_until_complete(server.mailserver.start_server())

Thread(target = startMailServer).start()

server.listen("0.0.0.0", 3008, ssl = sslctx)