const crockford = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";

function newUlid(): string {
  const bytes = new Uint8Array(16);
  let timestamp = Date.now();
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = timestamp & 0xff;
    timestamp = Math.floor(timestamp / 256);
  }
  crypto.getRandomValues(bytes.subarray(6));

  let encoded = "";
  let buffer = 0;
  let bits = 2;
  for (const byte of bytes) {
    buffer = (buffer << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      bits -= 5;
      encoded += crockford[(buffer >> bits) & 31];
      buffer &= (1 << bits) - 1;
    }
  }
  if (encoded.length !== 26) throw new Error("无法生成有效的 ULID。");
  return encoded;
}

function newStatusCredential(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

/** 在发起不可撤销操作前由浏览器生成，以便提交响应丢失时仍能查询工作单。 */
export function createDeletionRecoveryMaterial(): {
  request_id: string;
  status_credential: string;
} {
  return { request_id: newUlid(), status_credential: newStatusCredential() };
}
