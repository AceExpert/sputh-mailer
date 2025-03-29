import ws
import json

from typing import Any

from crypt import ECC, private_key
from models import Channel
from utils import gen_token

userData = {
    'anshul': {
        'pswd': 'Anshul@7329',
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
        self.ecc = ECC()

    async def on_ready(self):
        print("Server listening @ 0.0.0.0:3008")

    async def on_connect(self, client, path):
        print("Client connected @", client.remote_address)
        self.open_channels[client.remote_address] = Channel(
            client = client, 
            session_token = gen_token(), 
            auth = False
        )

    async def on_message(self, message):
        if message.client.remote_address in self.open_channels:
            self.loop.create_task(self.on_client_message(self.open_channels[message.client.remote_address], message))

    async def on_client_message(self, channel: Channel, message):
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

        else:
            
            if data == 're':
                channel.current_key = None

    async def auth_req(self, channel: Channel, data: dict):
        if data.user in userData and userData[data.user]['pswd'] == data.pswd:
            channel.auth = True
            channel.user = data.user
            await self.send_msg(channel.client, {'auth': 1}, channel.pub_key)
        else:
            await self.send_msg(channel.client, {'auth': 0}, channel.pub_key)

    async def send_msg(self, client, data, key):
        await client.send(data = {'en': self.ecc.encrypt(json.dumps(data), key)})

    async def on_disconnect(self, client, code, reason):
        await self.end_connection(client)

    async def on_close(self, client, code, reason):
        await self.end_connection(client)

    async def end_connection(self, client):
        try:
            client.close()
            del self.open_channels[client.remote_address]
        except Exception:
            pass

server = SputhMailer()
server.listen("cybertron", 3008)