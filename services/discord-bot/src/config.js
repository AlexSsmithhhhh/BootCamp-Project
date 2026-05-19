import path from 'node:path';

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required.`);
  }
  return value;
}

function optionalCsv(name) {
  return new Set(
    (process.env[name] ?? '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function optionalNumber(name, fallback) {
  const value = Number(process.env[name]);
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

const runningOnRailway = Boolean(process.env.RAILWAY_ENVIRONMENT);
const defaultDataDir = runningOnRailway
  ? (process.env.RAILWAY_VOLUME_MOUNT_PATH || '/app/data')
  : path.resolve('data');

export const config = {
  token: requiredEnv('DISCORD_TOKEN'),
  clientId: requiredEnv('DISCORD_CLIENT_ID'),
  guildId: requiredEnv('DISCORD_GUILD_ID'),
  dataPath:
    process.env.LEADERBOARD_DATA_PATH
    || process.env.DISCORD_LEADERBOARD_DATA_PATH
    || path.join(defaultDataDir, 'discord-leaderboard.json'),
  enableMessageContentIntent: process.env.DISCORD_ENABLE_MESSAGE_CONTENT_INTENT !== 'false',
  workingChannelIds: optionalCsv('LEADERBOARD_WORKING_CHANNEL_IDS'),
  ignoredChannelIds: optionalCsv('LEADERBOARD_IGNORED_CHANNEL_IDS'),
  dashboardChannelId:
    process.env.LEADERBOARD_CHANNEL_ID
    || process.env.DISCORD_LEADERBOARD_CHANNEL_ID
    || process.env.DASHBOARD_CHANNEL_ID
    || null,
  mentorRoleNames: (
    process.env.LEADERBOARD_MENTOR_ROLE_NAMES
    || 'mentor,support,ментор,саппорт,наставник'
  )
    .split(',')
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean),
  updateEveryMs: optionalNumber('LEADERBOARD_UPDATE_EVERY_MS', 5 * 60 * 1000),
  messageMinLength: optionalNumber('LEADERBOARD_MESSAGE_MIN_LENGTH', 20),
  messageMinWords: optionalNumber('LEADERBOARD_MESSAGE_MIN_WORDS', 3),
  stageMinMs: optionalNumber('LEADERBOARD_STAGE_MIN_MS', 15 * 60 * 1000),
  timeZone: process.env.LEADERBOARD_TIME_ZONE || 'Europe/Kiev',
  scores: {
    message: 2,
    messageDailyCap: 30,
    mentorReaction: 10,
    mentorReactionDailyCap: 50,
    stage: 25,
  },
};
