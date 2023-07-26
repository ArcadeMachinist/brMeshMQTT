const { spawn } = require("child_process");
const mqtt = require("mqtt");
const client = mqtt.connect("mqtt://x.x.x.x"); // Your MQTT server IP
let my_key = [0xAA, 0xBB, 0xCC, 0xDD];         // Your unique Mesh key - see README


let default_key = [0x5e, 0x36, 0x7b, 0xc4];
const BLE_CMD_RETRY_CNT = 1;
const BLE_CMD_ADVERTISE_LENGTH = 3000; 
const DEFAULT_BLE_FASTCON_ADDRESS = [0xC1, 0xC2, 0xC3];

let SEND_SEQ = 0;
let SEND_COUNT = 1;


function package_ble_fastcon_body (i, i2, sequence, safe_key, forward, data, key) {

    let body = new Array();
    body[0] = (i2 & 0b1111) << 0 | (i & 0b111) << 4 | (forward & 0xff) << 7;
    body[1] = sequence & 0xff;
    body[2] = safe_key;
    body[3] = 0; // checksum
    body = body.concat(data);

    let checksum = 0;
    for (j = 0; j < body.length; j ++) {
        if (j == 3) continue;
        checksum = (checksum + body[j]) & 0xff;
    }
    body[3] = checksum;

    // pad payload with zeros
    for (j = 0; j < (12 - data.length); j++) body = body.concat(0);

    for (j = 0; j < 4; j ++) {
        body[j] = default_key[j & 3] ^ body[j];        
    }
    for (j = 0; j < 12; j ++) {
        body[4 + j] = my_key[j & 3] ^ body[4 + j]; 
    }
    return body;
}

function get_payload_with_inner_retry(i, data, i2, key, forward, use_22_data) {

    SEND_COUNT++;
    SEND_SEQ = SEND_COUNT & 0xff;
    let safe_key = 0xff;
    if (key[0] == 0 || key[1] == 0 || key[2] == 0 || key[3] == 0) {
    } else {
        safe_key = key[3];
    }
    if (use_22_data) {
        console.log("Ooops! use_22_data");
        return -1;
    } else {
        return package_ble_fastcon_body(i, i2, SEND_SEQ, safe_key, forward, data, key);
    }

}

function get_rf_payload(addr, data) {

    let data_offset = 0x12;
    let inverse_offset = 0x0f;
    let result_data_size = data_offset + addr.length + data.length; 
    let resultbuf = [];

    resultbuf[0x0f] = 0x71;
    resultbuf[0x10] = 0x0f;
    resultbuf[0x11] = 0x55;

    console.log("");
    console.log("get_rf_payload");
    console.log("------------------------");
    console.log("addr: "+Buffer.from(addr).toString('hex'));
    console.log("data: "+Buffer.from(data).toString('hex'));
    for (j = 0; j < addr.length; j++) {
        resultbuf[data_offset + addr.length - j - 1] = addr[j];
    }

    for (j = 0; j < data.length; j++ ) {
        resultbuf[data_offset + addr.length + j] = data[j];
    }
    console.log("inverse_offset: "+ inverse_offset);
    console.log("inverse_offset addr.len + 3: "+ (inverse_offset +  addr.length + 3));
    for (let i = inverse_offset; i < inverse_offset +  addr.length + 3; i++ ) {
        resultbuf[i] = reverse_8(resultbuf[i]);
    }

    let crc = crc16(addr, data);
    resultbuf[result_data_size] = crc & 0xff;
    resultbuf[result_data_size+1] = (crc >> 8) & 0xff;
    return resultbuf;
}

function reverse_8(d) {
    let result = 0;
    for (let k = 0; k < 8; k++ ) {
        result |= ((d >> k) & 1) << (7 - k);
    }
    return result;
}

function reverse_16(d) {
    let result = 0;
    for (let k = 0; k < 16; k++ ) {
        result |= ((d >> k) & 1) << (15 - k);
    }
    return result;
}

function crc16(addr, data) {
    let crc = 0xffff;

    for (let i = addr.length - 1; i >= 0; i--) {
        crc ^= addr[i] << 8;
        for (let _ = 0; _ < 4; _++) {
            let tmp = crc << 1;

            if ((crc & 0x8000) !== 0) {
                tmp ^= 0x1021;
            }

            crc = tmp << 1;
            if ((tmp & 0x8000) !== 0) {
                crc ^= 0x1021;
            }
        }
    }

    for (let i = 0; i < data.length; i++) {
        crc ^= reverse_8(data[i]) << 8;
        for (let _ = 0; _ < 4; _++) {
            let tmp = crc << 1;

            if ((crc & 0x8000) !== 0) {
                tmp ^= 0x1021;
            }

            crc = tmp << 1;
            if ((tmp & 0x8000) !== 0) {
                crc ^= 0x1021;
            }
        }
    }

    crc = ~reverse_16(crc) & 0xffff;
    return crc;
}

function do_generate_command(i, data, key, _retry_count, _send_interval, forward, use_default_adapter, use_22_data, i2) {
    
    let i2_ = Math.max(i2,0);
    let payload = get_payload_with_inner_retry(i, data, i2_, key, forward, use_22_data);


    payload = get_rf_payload(DEFAULT_BLE_FASTCON_ADDRESS, payload);

    let whiteningContext = new Uint32Array(7);
    whiteningInit(0x25, whiteningContext);
    payload = whiteningEncode(payload, whiteningContext);
    payload = payload.slice(0xf);
    return payload;
}

function whiteningInit(val, ctx) {
    let v0 = [(val >> 5), (val >> 4), (val >> 3), (val >> 2)];
    ctx.f_0x0 = 1;
    ctx.f_0x4 = v0[0] & 1;
    ctx.f_0x8 = v0[1] & 1;
    ctx.f_0xc = v0[2] & 1;
    ctx.f_0x10 = v0[3] & 1;
    ctx.f_0x14 = (val >> 1) & 1;
    ctx.f_0x18 = val & 1;
}

function whiteningEncode(data, ctx) {
    let result = [];
    result = result.concat(data);
    for (let i  = 0; i < result.length; i++) {
        let varC = ctx.f_0xc;
        let var14 = ctx.f_0x14;
        let var18 = ctx.f_0x18;
        let var10 = ctx.f_0x10;
        let var8 = var14 ^ ctx.f_0x8;
        let var4 = var10 ^ ctx.f_0x4;
        let _var = var18 ^ varC;
        let var0 = _var ^ ctx.f_0x0;

        let c = result[i];
        result[i] = ((c & 0x80) ^ ((var8 ^ var18) << 7) & 0xff)
            + ((c & 0x40) ^ (var0 << 6) & 0xff)
            + ((c & 0x20) ^ (var4 << 5) & 0xff)
            + ((c & 0x10) ^ (var8 << 4) & 0xff)
            + ((c & 0x08) ^ (_var << 3) & 0xff)
            + ((c & 0x04) ^ (var10 << 2) & 0xff)
            + ((c & 0x02) ^ (var14 << 1) & 0xff)
            + ((c & 0x01) ^ (var18 << 0) & 0xff);

        ctx.f_0x8 = var4;
        ctx.f_0xc = var8;
        ctx.f_0x10 = var8 ^ varC;
        ctx.f_0x14 = var0 ^ var10;
        ctx.f_0x18 = var4 ^ var14;
        ctx.f_0x0 = var8 ^ var18;
        ctx.f_0x4 = var0;
    }
    return result;
}

function single_control(addr, key, data, delay) {
    let result = [];
    result[0] = 2 | (((0xfffffff & (data.length + 1)) << 4) & 0xff);
    result[1] = addr & 0xff;
    result = result.concat(data);

    let ble_adv_data = [0x02,0x01,0x1A,0x1B,0xFF,0xF0,0xFF];
    ble_adv_cmd = ble_adv_data.concat(do_generate_command(5, 
                          result, 
                          key,
                          BLE_CMD_RETRY_CNT,
                          BLE_CMD_ADVERTISE_LENGTH,
                          true, // forward?
                          true, // use_default_adapter
                          (addr > 256) & 0xff, // use_22_data
                          (addr / 256) & 0xff  // i2
                        ));
    console.log("Adv-Cmd          : btmgmt add-adv -d "+ Buffer.from(ble_adv_cmd).toString('hex') + " 1");  
    let cmd = spawn("btmgmt", ["add-adv", "-d", Buffer.from(ble_adv_cmd).toString('hex'), 1]);
}



class Light {
    constructor(mesh_key, device_id) {
        this.id = device_id;
        this.key = mesh_key;
    }

    setOnOff(on, brightness) {
	console.log("brightness: "+brightness);
        let command = new Array(1).fill(0);
        command[0] = 0;
	if (on) { command[0] = 128 + (brightness & 127) };
        single_control(this.id, this.key, command, 0);
    }
    Brightness(on, brightness) {
        let command = new Array(1).fill(0);
        command[0] = 0;
        if (on) command[0] = (brightness & 127);
        single_control(this.id, this.key, command, 0);
    }
    WarmWhite(on, brightness, i5, i6) {
	let command = new Array(6).fill(0);
        command[0] = 0;
	command[4] = i5 & 0xff;
	command[5] = i6 & 0xff;
        if (on) { command[0] = 128 + (brightness & 127) };
        single_control(this.id, this.key, command, 0);
    }
    Colored(on, brightness, r, g, b, abs) {
	let command = new Array(6).fill(0);
	let color_normalisation = 1;
	command[0] = 0;
        if (on) command[0]+=128;
        command[0]+=(brightness & 127);
	if (!abs) {
		color_normalisation = 255.0 / (r + g + b) ;
	}
	command[1] = (b * color_normalisation) & 0xff;
	command[2] = (r * color_normalisation) & 0xff;
	command[3] = (g * color_normalisation) & 0xff;
	single_control(this.id, this.key, command, 0);
    }
}


client.on("connect", () => {
  client.subscribe("presence", (err) => {
    if (!err) {
      client.publish("presence", "brMesh");
      client.subscribe("brMesh/#");
    }
  });
});

client.on("message", (topic, message,packet) => {
  if (topic.indexOf("/") > -1) {
        let topic_talks =  topic.split("/");
        console.log(topic_talks);
        if (topic_talks[0] == "brMesh") {
                let light = topic_talks[1];
                if (topic_talks[2] == "set") {
                        let myLight = new Light(my_key, light);
                        let brightness = 0;
                        console.log(packet.payload.toString());
                        let payload = JSON.parse(packet.payload.toString());
                        console.log(payload);
                        if (typeof payload.brightness != "undefined") {
                               // Map HA 3..255 brightness range to brMesh 1..127
                               let nb =  (payload.brightness - 3) * (127 - 1) / (255 - 3) + 1;
                               //console.log("nb: "+nb);
                               myLight.Brightness(1,nb);
                        } else if (typeof payload.color != "undefined") {
                               myLight.Colored(1, brightness, payload.color.r, payload.color.g, payload.color.b, true);
                        } else if (typeof payload.color_temp != "undefined") {
                               if (payload.color_temp == 500) {
                                myLight.WarmWhite(1,brightness,127,127);
                               }
                        } else {
                                if (typeof payload.state != "undefined") {
                                        if (payload.state == "ON") { // last state
                                                myLight.setOnOff(1,brightness);
                                        } else {
                                                myLight.setOnOff(0,0);
                                        }
                                }
                       }
                }
        }
  }
});

