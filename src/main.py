import json
import smtplib
import ssl

import ws

from typing import Any

from crypt import ECC, private_key
from models import Channel, DnsRecord, Interval
from utils import gen_token, get_dns_record, get_email
from mailcomposer import MailComposer

userData = {
    'anshul': {
        'pswd': 'Anshul@7329',
        'name': 'Anshul Singh',
        'extern': {
            'domains': [{'name': 'gmail.com', 'key': ''}, {'name': 'kgpian.iitkgp.ac.in', 'key': ''}]
        }
    }
}

ws.Message.client = property(lambda self: self.author)

class SputhMailer(ws.ServerSocket):

    def __init__(self):
        super().__init__()
        self.open_channels: dict[Any, Channel] = {}
        self.ssl_ctx = ssl.SSLContext()
        self.smtp_client = smtplib.SMTP()
        self.ecc = ECC()

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
            hb_timer = hbinterval
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
                #print(fdata)
                if 'action' in fdata:
                    
                    if fdata.action == 0:
                        channel.pub_key = bytes(bytearray(fdata.key))
                        (channel.current_key, client_pub_key) = self.ecc.generate_keys()
                        await channel.client.send(data = {'chan': self.ecc.encrypt_s1(json.dumps([*client_pub_key]))})

                    elif fdata.action == 1:
                        await self.auth_req(channel, fdata)

                    elif fdata.action == 2:
                        await self.send_mail(channel, fdata['data'])

                    elif fdata.action == -1:
                        await self.sign_up(channel, fdata['data'])
        else:
            
            if data == 're':
                channel.current_key = None

    async def auth_req(self, channel: Channel, data: dict):
        if data.user in userData and userData[data.user]['pswd'] == data.pswd:
            channel.auth = True
            channel.user = data.user
            channel.info = ws.Object({
                'user': data.user,
                'name': userData[data.user]['name'],
                'extern': userData[data.user]['extern']
            })
            await self.send_msg(channel.client, {'auth': 1}, channel.pub_key)
        else:
            await self.send_msg(channel.client, {'auth': 0}, channel.pub_key)

    async def send_mail(self, channel: Channel, data: dict):
        #from_address = get_email(data['from'])
        from_dom = data['fromDomain'][0]
        to_address = get_email(data['toAddr'])[0]
        mail = MailComposer(channel.info.name, channel.info.user, from_dom, to = to_address, subject = data.get("subject", None), content = data.get('content', None))
        mail.set_html(data['html'] if 'html' in data and data.get('html', None) else data.get('content', None))
        mail.sign('cytroid.in', 'dragon', to_address)
        self.records: list[DnsRecord] = get_dns_record(to_address.split("@")[1], "MX")
        self.smtp_client.connect(self.records[0].value[:-1])
        self.smtp_client.helo(from_dom)
        self.smtp_client.starttls(context = self.ssl_ctx)
        self.smtp_client.sendmail(f'{channel.info.user}@{from_dom}', to_address, mail.get_bytes())
        self.smtp_client.close()

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
server.listen("0.0.0.0", 3008)