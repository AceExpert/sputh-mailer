const ecc = require("eccrypto");

const {privateKey, symm, symmRev} = require("../constants");

class Encrypter {

    constructor() {

    }

    encryptS1(data) {

    }

    encrypt(data, pubkey) {

    }

    decryptS1(data) {

    }

    decryptS2(data, key) {

    }

    decrypt(data, pubkey) {
        return this.decryptS2(this.decryptS1(data), pubkey);
    }

    generateKeys() {

    }
}

class ECC extends Encrypter {

    constructor(symMap = symm, symRevMap = symmRev) {
        super();
        this.symm = symMap;
        this.symmRev = symRevMap;
    }

    encryptS1(data) {
        let ck1 = [...data];
        [...data].forEach((l, i) => ck1[i] = this.symm[l]);
        return ck1.join("");
    }

    decryptS1(data) {
        let ck1 = [...data];
        [...data].forEach((l, i) => ck1[i] = this.symmRev[l]);
        return ck1.join("");
    }

    decryptS2(data, key) {
        let encOpt = JSON.parse(data);
        let fd = {
            iv: Buffer.from(encOpt[0]),
            ephemPublicKey: Buffer.from(encOpt[1]),
            ciphertext: Buffer.from(encOpt[2]),
            mac: Buffer.from(encOpt[3])
        }
        return ecc.decrypt(key, fd).then(decrypted => decrypted.toString());
    }

    decrypt(data, key = privateKey) {
        return this.decryptS2(this.decryptS1(data), key);
    }

    encrypt(data, key) {
        return ecc.encrypt(key, Buffer.from(data)).then(encrypted => {
            let d = JSON.stringify(Object.keys(encrypted).map(k => [...encrypted[k]]));
            return this.encryptS1(d);
        })
    }

    generateKeys() {
        let privKey = ecc.generatePrivate();
        let pubKey = ecc.getPublic(privKey);
        return [privKey, pubKey]
    }

}

module.exports = {
    ecc: new ECC(), 
}