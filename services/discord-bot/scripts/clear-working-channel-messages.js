const token = process.env.DISCORD_TOKEN;
const workingChannelIds = (process.env.LEADERBOARD_WORKING_CHANNEL_IDS || '')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);

if (!token) {
  throw new Error('DISCORD_TOKEN is required.');
}
if (workingChannelIds.length === 0) {
  throw new Error('LEADERBOARD_WORKING_CHANNEL_IDS is required.');
}

const discordEpoch = 1420070400000n;
const twoWeeksMs = 14 * 24 * 60 * 60 * 1000;

for (const channelId of workingChannelIds) {
  const channel = await discordRequest('GET', `/channels/${channelId}`);
  const deleted = await clearChannel(channelId);
  console.log(`${channel.name}: deleted ${deleted} messages`);
}

async function clearChannel(channelId) {
  let totalDeleted = 0;

  while (true) {
    const messages = await discordRequest('GET', `/channels/${channelId}/messages?limit=100`);
    if (messages.length === 0) {
      return totalDeleted;
    }

    const freshMessages = messages.filter((message) => canBulkDelete(message.id));
    const oldMessages = messages.filter((message) => !canBulkDelete(message.id));

    for (let index = 0; index < freshMessages.length; index += 100) {
      const batch = freshMessages.slice(index, index + 100);
      if (batch.length === 1) {
        await discordRequest('DELETE', `/channels/${channelId}/messages/${batch[0].id}`, null, [204, 404]);
      } else if (batch.length > 1) {
        await discordRequest(
          'POST',
          `/channels/${channelId}/messages/bulk-delete`,
          { messages: batch.map((message) => message.id) },
          [204],
        );
      }
      totalDeleted += batch.length;
      await sleep(1000);
    }

    for (const message of oldMessages) {
      await discordRequest('DELETE', `/channels/${channelId}/messages/${message.id}`, null, [204, 404]);
      totalDeleted += 1;
      await sleep(1000);
    }
  }
}

function canBulkDelete(messageId) {
  const createdAt = Number((BigInt(messageId) >> 22n) + discordEpoch);
  return Date.now() - createdAt < twoWeeksMs;
}

async function discordRequest(method, path, body = null, okStatuses = [200, 201, 204]) {
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    const response = await fetch(`https://discord.com/api/v10${path}`, {
      method,
      headers: {
        Authorization: `Bot ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    const text = await response.text();
    if (okStatuses.includes(response.status)) {
      return text ? JSON.parse(text) : null;
    }
    if (response.status === 429) {
      await sleep(retryAfterMs(text));
      continue;
    }
    throw new Error(`${method} ${path} ${response.status}: ${text}`);
  }

  throw new Error(`${method} ${path} failed after rate-limit retries.`);
}

function retryAfterMs(responseText) {
  try {
    return Math.ceil(JSON.parse(responseText).retry_after * 1000) + 250;
  } catch {
    return 1000;
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
