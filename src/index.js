const ws = require("ws");
const nodemailer = require("nodemailer");

const {ecc} = require("./encrypter");

let client = nodemailer.createTransport({
    host: "alt1.gmail-smtp-in.l.google.com",
    port: 587,
    secure: true,
})

client.sendMail({
    envelope: { from: "support@cytroid.in", to: "very.anshul@gmail.com" },
    from: "Cytroid <support@cytroid.in>",
    to: '"Anshul Singh" <very.anshul@gmail.com>',
    subject: "Cytroid OTP",
    text: "Your OTP is 8990",
    messageId: `<${Math.random()}@sayutel.com>`
}).then(console.log)

console.log("Sending...");

//client.close();

let userData = {
    'anshul': {
        pswd: 'Anshul@7329',
        extern: {
            domains: [{name: 'gmail.com', key: ''}, {name: 'kgpian.iitkgp.ac.in', key: ''}]
        }
    }
}

function sendData(client, data, key) {
    ecc.encrypt(JSON.stringify(data), key).then(val => {
        client.send(JSON.stringify({'en': val}))
    })
}
/*
let server = new ws.WebSocketServer({
    port: 3008,
    path: "/mail"
})

let openChannels = {}

server.on("connection", (client, req) => {
    console.log("Connected client @ ", req.socket.remoteAddress + ':' + req.socket.remotePort);
    let session = Math.random.toString();
    let pubKey = null;
    let key = null;
    let auth = false;
    openChannels[session] = {
        client,
        key: null,
        auth: false,
        pubkey: null,
    }
    client.on("message", msg => {
        try {
            let data = JSON.parse(msg.toString());
            if(data['en']) {
                let dkey = key ?? undefined;
                ecc.decrypt(data.en, dkey).then(val => {
                    let fdata = JSON.parse(val);
                    console.log(fdata);
                    if(fdata['action'] !== undefined) {
                        if(fdata.action === 0) {
                            openChannels[session].pubkey = Buffer.from(fdata.key);
                            let newKeys = ecc.generateKeys();
                            openChannels[session].key = newKeys[0];
                            key = openChannels[session].key;
                            pubKey = openChannels[session].pubkey;
                            client.send(JSON.stringify({'chan': ecc.encryptS1(JSON.stringify([...newKeys[1]]))}))
                        }
                        else {
                            if(fdata.action === 1) {
                                if(userData[fdata.user]?.pswd === fdata.pswd) {
                                    openChannels[session].auth = true;
                                    auth = true;
                                    sendData(client, {'auth': 1}, pubKey);
                                } else {
                                    sendData(client, {'auth': 0}, pubKey);
                                }
                            } else if (fdata.action === 2) {

                            }
                        }
                    }
                })
            }

        } catch (e) {
            console.error(e);
        }
    })
})

server.on("listening", () => {
    console.log("Sputh Mailer live @ ws://0.0.0.0:3008/mail")
})
*/
