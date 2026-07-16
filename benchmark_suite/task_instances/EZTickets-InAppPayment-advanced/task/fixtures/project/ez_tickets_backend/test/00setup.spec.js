const bufferModule = require('buffer');

if (!bufferModule.SlowBuffer) {
    bufferModule.SlowBuffer = bufferModule.Buffer;
}
