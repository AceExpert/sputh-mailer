import asyncio
import ssl
import socket
import enum
import re

sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
# sslctx.load_cert_chain('/etc/letsencrypt/archive/sayutel.com/cert1.pem', '/etc/letsencrypt/archive/sayutel.com/privkey1.pem')

class CmdState(enum.Enum):
    START = 0
    MIDDLE = 1
    MULTILINE = 2
    MULTILINE_LAST = 3

class SMTPClientInfo:

    def __init__(self):
        self.ehlo_domain: str = None
        self.tls_attempt: bool = False
        self.is_tls: bool = False
        self.mail_from: str = None
        self.mail_data: bytes = b''
        self.rcpt_to: list[str] = []

class SayutelMailServer:

    loop: asyncio.AbstractEventLoop
    server: asyncio.Server

    class ClientProtocol(asyncio.Protocol):

        def __init__(self, mailserver, transport):
            super().__init__()
            self.mailserver: SayutelMailServer = mailserver
            self.transport = transport
            transport.write(b"220 sayutel.com Sayutel ESMTPS Server\r\n")

            self.info = SMTPClientInfo()

            self.buff_list = []
            self.buff = b''
            self.cmds = []
            self.current_cmd = ''
            self.state = CmdState.START
            
        def connection_made(self, transport):
            pass
            
        def data_received(self, data: bytes):
            self.buff += data
            parts = self.buff.split(b'\r\n')
            i = 0
            for part in parts:
                if i < len(parts) - 1:
                    print(part)
                    if len(part) >= 6:
                        if part[:4].lower() == b'ehlo':
                            if 'ehlo' not in self.cmds:
                                self.cmds.append('ehlo')
                            self.info.ehlo_domain = part[5:].strip().decode()
                            self.transport.write(
                                b'250-sayutel.com Hello ' + self.info.ehlo_domain.encode() + b'\r\n'
                                b'250-SIZE 157286400\r\n'
                                b'250-STARTTLS\r\n'
                                b'250-PIPELINING\r\n'
                                b'250-CHUNKING\r\n'
                                b'250-SMTPUTF8\r\n'
                                b'250 8BITMIME\r\n'
                            )
                        elif part.lower().strip() == b'starttls':
                            print("yes")
                            self.transport.write(b"220 Yes go ahead\r\n")
                            self.info.tls_attempt = True
                            self.mailserver.loop.create_task(self.mailserver.loop.start_tls(self.transport, self, sslcontext = sslctx, server_side = True))

                        elif b':' in part:
                            cmd, params = part.split(b':', 1)
                            cmd_normal = cmd.lower().strip()
                            if cmd_normal == b'mail from':
                                for param in params.split():
                                    f_param = param.strip()
                                    if f_param.startswith(b'<') and f_param.endswith(b'>'):
                                        self.info.mail_from = f_param[1:-1].decode()
                            elif cmd_normal == b'rcpt to':
                                for param in params.split():
                                    f_param = param.strip()
                                    if f_param.startswith(b'<') and f_param.endswith(b'>'):
                                        self.info.rcpt_to.append(f_param[1:-1].decode())
                else:
                    self.buff = part

                i += 1


        def eof_received(self):
            print("CONN EOF CL")
            pass
        
        def connection_lost(self, exc: Exception):
            print(exc)
            print("CONN LOST CL")
            pass
    
    class ServerProtocol(asyncio.Protocol):

        def __init__(self, mailserver):
            super().__init__()
            self.mailserver: SayutelMailServer = mailserver

        def connection_made(self, transport):
            transport.set_protocol(self.mailserver.ClientProtocol(self.mailserver, transport))
        
        def data_received(self, data: bytes):
            pass
    
        def eof_received(self):
            pass
        
        def connection_lost(self, exc: Exception):
            pass
        
    def __init__(self, loop = None):
        self.loop = loop or asyncio.new_event_loop()
        self.connections = []

    async def start_server(self):
        self.server = await self.loop.create_server(
            lambda: self.ServerProtocol(self), 
            '0.0.0.0', 25, 
            family = socket.AF_INET, backlog = 4096
        )
        
        await self.server.start_serving()
        await self.server.serve_forever()

mailserver = SayutelMailServer()
mailserver.loop.run_until_complete(mailserver.start_server())