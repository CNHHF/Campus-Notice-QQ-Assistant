// Encode locally using the installed official plugin's QR library. No external QR service.
const fs = require('node:fs');
const path = require('node:path');
const input = JSON.parse(fs.readFileSync(0,'utf8'));
const QRCode = require(input.module);
const Level = require(path.join(input.module,'QRErrorCorrectLevel'));
const qr = new QRCode(-1,Level.M);
qr.addData(input.text);qr.make();
const n=qr.getModuleCount(), size=n+8;
let commands='';
for(let y=0;y<n;y++)for(let x=0;x<n;x++)if(qr.isDark(y,x))commands+=`M${x+4} ${y+4}h1v1h-1z`;
process.stdout.write(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" shape-rendering="crispEdges"><rect width="${size}" height="${size}" fill="white"/><path d="${commands}" fill="#102b22"/></svg>`);
