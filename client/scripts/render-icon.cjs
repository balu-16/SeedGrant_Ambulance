const { Resvg } = require('@resvg/resvg-js');
const fs = require('node:fs');
const svg = fs.readFileSync('assets/icons/app-icon.svg', 'utf8');
fs.writeFileSync('assets/images/app-icon.png', new Resvg(svg).render().asPng());
