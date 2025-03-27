## Sputh Mailer

For encryption to work, bundle the encrypter for the email client (sputh-mail / sayumail) as well using browserify
```bash
browserify ./src/encrypter/index.js -o bundle.js
```
Add
```js
window.Buffer = Buffer;
window.publicKey = publicKey;
window.ecc = new ECC();
```
_______