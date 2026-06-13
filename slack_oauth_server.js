const express = require("express");
const crypto = require("crypto");
require("dotenv").config();

const app = express();
const stateStore = new Map();
const port = Number(process.env.SLACK_OAUTH_PORT || 3000);

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

function pruneExpiredStates() {
  const now = Date.now();
  for (const [state, metadata] of stateStore.entries()) {
    if (now - metadata.timestamp > 10 * 60 * 1000) {
      stateStore.delete(state);
    }
  }
}

app.get("/slack/install", (req, res) => {
  pruneExpiredStates();

  const state = crypto.randomBytes(16).toString("hex");
  stateStore.set(state, { timestamp: Date.now() });

  const scopes = ["channels:read", "chat:write", "users:read"].join(",");

  const authUrl = new URL("https://slack.com/oauth/v2/authorize");
  authUrl.searchParams.set("client_id", requireEnv("SLACK_CLIENT_ID"));
  authUrl.searchParams.set("scope", scopes);
  authUrl.searchParams.set("redirect_uri", requireEnv("SLACK_REDIRECT_URI"));
  authUrl.searchParams.set("state", state);

  res.redirect(authUrl.toString());
});

app.get("/slack/oauth/callback", async (req, res) => {
  const { code, state, error } = req.query;

  if (error) {
    res.status(400).send(`Slack authorization failed: ${error}`);
    return;
  }

  if (!code || !state || !stateStore.has(state)) {
    res.status(400).send("Invalid or expired Slack OAuth state.");
    return;
  }

  stateStore.delete(state);

  const body = new URLSearchParams({
    client_id: requireEnv("SLACK_CLIENT_ID"),
    client_secret: requireEnv("SLACK_CLIENT_SECRET"),
    code: String(code),
    redirect_uri: requireEnv("SLACK_REDIRECT_URI"),
  });

  try {
    const slackResponse = await fetch("https://slack.com/api/oauth.v2.access", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });

    const payload = await slackResponse.json();
    if (!payload.ok) {
      res.status(400).json(payload);
      return;
    }

    const botToken = payload.access_token;
    const botUserId = payload.bot_user_id;
    const teamName = payload.team && payload.team.name;

    console.log("\nSlack OAuth install complete.");
    console.log(`Team: ${teamName || "Unknown"}`);
    console.log(`Bot user ID: ${botUserId || "Unknown"}`);
    console.log("\nAdd this to your .env file:");
    console.log(`SLACK_BOT_TOKEN=${botToken}`);
    console.log("SLACK_CHANNEL_ID=<your-channel-id>\n");

    res.type("html").send(`
      <h1>Slack install complete</h1>
      <p>Copy the generated <code>SLACK_BOT_TOKEN</code> from your terminal into <code>.env</code>.</p>
      <p>Then set <code>SLACK_CHANNEL_ID</code> to the channel where the automation should post.</p>
    `);
  } catch (err) {
    console.error("Slack OAuth token exchange failed:", err);
    res.status(500).send("Slack OAuth token exchange failed. Check the terminal logs.");
  }
});

app.get("/", (req, res) => {
  res.type("html").send(`
    <h1>OriginPulse Slack OAuth Helper</h1>
    <p><a href="/slack/install">Install Slack app</a></p>
  `);
});

app.listen(port, () => {
  console.log(`Slack OAuth helper running at http://localhost:${port}`);
  console.log(`Install URL: http://localhost:${port}/slack/install`);
});
