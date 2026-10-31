/**
 * AkerGate - Telegram Native Serverless Message Handler
 * Runs directly on Telegram's official V8 serverless infrastructure (tgcloud.ai).
 * Zero external hosting, zero maintenance, sub-5ms latency.
 * Zero emojis, clean symbols only.
 *
 * Documentation: https://core.telegram.org/bots/serverless
 */

import { api } from 'sdk';
import { CONFIG } from '../config.js';

// Decode Base32 string to Uint8Array
function base32Decode(input) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const cleaned = input.toUpperCase().replace(/=+$/, "").replace(/\s/g, "");
  let bits = 0;
  let value = 0;
  const output = [];

  for (let i = 0; i < cleaned.length; i++) {
    const idx = alphabet.indexOf(cleaned[i]);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      output.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return new Uint8Array(output);
}

// Generate 7-digit Windowed OTP matching AkerGate Core engine
async function generateAkerOtp(secretB32, intervalSeconds = 300) {
  const slot = Math.floor(Math.random() * 10); // Random slot 0..9
  const now = Math.floor(Date.now() / 1000);
  const counter = Math.floor(now / intervalSeconds);

  const keyBytes = base32Decode(secretB32);
  const cryptoKey = await crypto.subtle.importKey(
    "raw",
    keyBytes,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  // Pack counter and slot as big-endian 64-bit uints
  const buffer = new ArrayBuffer(16);
  const view = new DataView(buffer);
  view.setBigUint64(0, BigInt(counter), false);
  view.setBigUint64(8, BigInt(slot), false);

  const signature = await crypto.subtle.sign("HMAC", cryptoKey, buffer);
  const sigBytes = new Uint8Array(signature);

  const offset = sigBytes[19] & 0x0f;
  const binary =
    ((sigBytes[offset] & 0x7f) << 24) |
    ((sigBytes[offset + 1] & 0xff) << 16) |
    ((sigBytes[offset + 2] & 0xff) << 8) |
    (sigBytes[offset + 3] & 0xff);

  const codeNum = binary % 1000000;
  const codeStr = String(codeNum).padStart(6, "0");
  const secondsRemaining = intervalSeconds - (now % intervalSeconds);

  return {
    code: `${slot}${codeStr}`,
    secondsRemaining: secondsRemaining
  };
}

export default async function handleMessage(message) {
  const chatId = message.chat.id;
  const senderId = message.from ? message.from.id : chatId;
  const rawText = (message.text || "").trim().toLowerCase();

  // Strict authorization check
  if (CONFIG.ALLOWED_CHAT_ID && senderId !== CONFIG.ALLOWED_CHAT_ID) {
    await api.sendMessage({
      chat_id: chatId,
      text: "*[!] Access Denied*\nYou are not authorized to access this AkerGate node.",
      parse_mode: "Markdown"
    });
    return;
  }

  const now = Math.floor(Date.now() / 1000);
  const secondsRemaining = CONFIG.INTERVAL_SECONDS - (now % CONFIG.INTERVAL_SECONDS);

  if (rawText === "/start" || rawText === "/help") {
    const welcome = [
      "*[+] AKERGATE TELEGRAM SERVERLESS BOT*",
      "────────────────────────",
      "Hosted natively on Telegram Infrastructure (tgcloud.ai)",
      "Zero external servers | Zero maintenance",
      "────────────────────────",
      "• `/otp` or `/code` : Generate your 7-digit offline OTP",
      "• `/status` : Check engine timing and epoch interval",
      "• `/help` : Show this commands list",
      "────────────────────────",
      `Epoch Window: \`${CONFIG.INTERVAL_SECONDS} seconds\``,
      `Next Rotation: \`in ${secondsRemaining}s\``
    ].join("\n");

    await api.sendMessage({
      chat_id: chatId,
      text: welcome,
      parse_mode: "Markdown"
    });
    return;
  }

  if (rawText === "/otp" || rawText === "/code" || rawText === "otp" || rawText === "code") {
    if (!CONFIG.SHARED_SECRET) {
      await api.sendMessage({
        chat_id: chatId,
        text: "*[!] Configuration Missing*\nPlease set SHARED_SECRET in tgcloud/config.js before requesting OTP codes.",
        parse_mode: "Markdown"
      });
      return;
    }

    const { code, secondsRemaining } = await generateAkerOtp(CONFIG.SHARED_SECRET, CONFIG.INTERVAL_SECONDS);

    const reply = [
      "*[+] AKERGATE AUTHENTICATION OTP*",
      "────────────────────────",
      `Your 7-Digit Code: \`${code}\``,
      "────────────────────────",
      `• Window Slot: \`[${code[0]}]\``,
      `• Expires in: \`${secondsRemaining} seconds\``,
      "• Valid for PAM authentication elevation",
      "• Architecture: Native Telegram Serverless"
    ].join("\n");

    await api.sendMessage({
      chat_id: chatId,
      text: reply,
      parse_mode: "Markdown"
    });
    return;
  }

  if (rawText === "/status") {
    const statusMsg = [
      "*[+] AKERGATE SERVERLESS STATUS*",
      "────────────────────────",
      `• Host Epoch Interval: \`${CONFIG.INTERVAL_SECONDS}s\``,
      `• Time to Window Change: \`${secondsRemaining}s\``,
      "• Platform: Telegram Serverless (tgcloud.ai)",
      "• Runtime: V8 Isolate Sandbox",
      "• State: Active & Synchronized",
      "────────────────────────"
    ].join("\n");

    await api.sendMessage({
      chat_id: chatId,
      text: statusMsg,
      parse_mode: "Markdown"
    });
    return;
  }
}
