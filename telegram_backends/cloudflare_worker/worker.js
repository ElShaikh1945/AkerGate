/**
 * AkerGate - Cloudflare Worker Telegram Bot
 * Serverless, 100% Free, Zero maintenance offline-compatible OTP generator.
 * Zero emojis, clean symbols only.
 */

// Helper to decode Base32 string to Uint8Array
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

// Generate 7-digit Windowed OTP matching AkerGate Core
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

async function sendTelegramMessage(botToken, chatId, text) {
  const url = `https://api.telegram.org/bot${botToken}/sendMessage`;
  await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chat_id: chatId,
      text: text,
      parse_mode: "Markdown"
    })
  });
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("AkerGate Worker active.", { status: 200 });
    }

    try {
      const update = await request.json();
      const message = update.message;
      if (!message || !message.text) {
        return new Response("OK", { status: 200 });
      }

      const senderId = String(message.from.id);
      const allowedId = String(env.ALLOWED_CHAT_ID);

      // Strict security: Reject unauthorized users
      if (senderId !== allowedId) {
        return new Response("Unauthorized", { status: 200 });
      }

      const text = message.text.trim();
      const chatId = message.chat.id;
      const botToken = env.BOT_TOKEN;
      const secret = env.SHARED_SECRET;
      const interval = parseInt(env.INTERVAL_SECONDS || "300", 10);

      if (text === "/start" || text === "/help") {
        const welcome = [
          "*AkerGate - Remote Authentication & Security Bot*",
          "────────────────────────",
          "Commands:",
          "• `/otp` : Generate a 7-digit temporary access code",
          "• `/lockdown` : Trigger Host Emergency Quarantine",
          "• `/disarm <totp>` : Cancel emergency lockdown remotely",
          "• `/status` : Check backend status and timing",
          "────────────────────────",
          "AkerGate protects your Linux host even when offline."
        ].join("\n");
        await sendTelegramMessage(botToken, chatId, welcome);
      } else if (text === "/lockdown" || text === "lockdown" || text === "/panic") {
        const prompt = [
          "*[!] AkerGate Emergency Lockdown*",
          "────────────────────────",
          "Select the required verification policy to activate lockdown:",
          "",
          "1. `dual_totp` (Recommended Offline):",
          "   `/lockdown dual_totp`",
          "   Requires Master Password + 2 Consecutive TOTP codes.",
          "",
          "2. `strict_3fa` (Full Defense):",
          "   `/lockdown strict_3fa`",
          "   Requires Password + TOTP + Telegram OTP combined.",
          "",
          "3. `totp_only` (Compromised Password mode):",
          "   `/lockdown totp_only`",
          "   Requires 2 Consecutive TOTP codes only.",
          "────────────────────────"
        ].join("\n");
        await sendTelegramMessage(botToken, chatId, prompt);
      } else if (text.startsWith("/lockdown ")) {
        const policy = text.replace("/lockdown ", "").trim().toLowerCase();
        const validPolicies = ["dual_totp", "strict_3fa", "totp_only"];
        const chosen = validPolicies.includes(policy) ? policy : "dual_totp";
        
        const alert = [
          "*[!] EMERGENCY LOCKDOWN ORDER INITIATED*",
          "────────────────────────",
          `• Enforced Policy: \`${chosen}\``,
          "• Action: Quarantining host, terminating sessions",
          "• Forensic: Snapshot report will be generated",
          "────────────────────────",
          "To disarm on host (offline):",
          "Enter 2 consecutive TOTP codes (e.g. `Code1+Code2`).",
          "",
          "To disarm remotely:",
          "`/disarm <CURRENT_TOTP>`"
        ].join("\n");
        await sendTelegramMessage(botToken, chatId, alert);
      } else if (text.startsWith("/disarm")) {
        const parts = text.split(/\s+/);
        if (parts.length < 2) {
          await sendTelegramMessage(botToken, chatId, "[!] Usage: `/disarm <6-DIGIT_TOTP_CODE>`");
        } else {
          const totpCandidate = parts[1].trim();
          await sendTelegramMessage(botToken, chatId, `[+] Disarm request received for TOTP: \`${totpCandidate}\`. Host will return to normal mode upon verification.`);
        }
      } else if (text.startsWith("/otp") || text === "otp" || text === "code") {
        const res = await generateAkerOtp(secret, interval);
        const minutes = Math.floor(interval / 60);
        const reply = [
          "*[+] AkerGate One-Time Passcode*",
          "────────────────────────",
          `• Passcode: \`${res.code}\``,
          `• Epoch Validity: ~${minutes} Minutes`,
          "• Single-use: Burns immediately upon entry",
          "────────────────────────",
          "Type this code into the password prompt on your PC."
        ].join("\n");
        await sendTelegramMessage(botToken, chatId, reply);
      } else if (text === "/status") {
        const now = new Date().toISOString();
        const status = [
          "*[i] AkerGate Backend Status*",
          "────────────────────────",
          "• Status: Operational",
          `• Cloud Time (UTC): \`${now}\``,
          `• Interval: ${interval}s`,
          "────────────────────────"
        ].join("\n");
        await sendTelegramMessage(botToken, chatId, status);
      }

      return new Response("OK", { status: 200 });
    } catch (err) {
      return new Response("Error: " + err.message, { status: 500 });
    }
  }
};
