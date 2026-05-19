const token = process.env.DISCORD_TOKEN;
const channelId = process.env.LEADERBOARD_CHANNEL_ID || process.env.DISCORD_LEADERBOARD_CHANNEL_ID;

if (!token || !channelId) {
  throw new Error('DISCORD_TOKEN and LEADERBOARD_CHANNEL_ID are required.');
}

const response = await fetch(`https://discord.com/api/v10/channels/${channelId}/messages?limit=5`, {
  headers: {
    Authorization: `Bot ${token}`,
  },
});

if (!response.ok) {
  throw new Error(`${response.status}: ${await response.text()}`);
}

const messages = await response.json();

for (const message of messages) {
  const embedTitle = message.embeds?.[0]?.title ?? '';
  console.log([
    message.id,
    message.author?.username,
    message.timestamp,
    embedTitle,
    (message.content || '').slice(0, 60),
  ].join('\t'));
}
