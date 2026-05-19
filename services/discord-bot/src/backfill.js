import {
  isMentorOrSupport,
  isPositiveReaction,
  isSubstantiveMessage,
  userLikeFromMemberOrUser,
} from './leaderboard.js';

export async function backfillLeaderboardHistory(client, storage, config) {
  if (!config.backfillOnStartup || config.workingChannelIds.size === 0) {
    return {
      enabled: false,
      scannedMessages: 0,
      awardedMessagePoints: 0,
      awardedReactionPoints: 0,
    };
  }

  const cutoffMs = Date.now() - (config.backfillDays * 24 * 60 * 60 * 1000);
  const totals = {
    enabled: true,
    channels: 0,
    scannedMessages: 0,
    awardedMessages: 0,
    duplicateMessages: 0,
    awardedMessagePoints: 0,
    awardedReactions: 0,
    duplicateReactions: 0,
    awardedReactionPoints: 0,
  };

  for (const channelId of config.workingChannelIds) {
    const channel = await fetchTextChannel(client, channelId);
    if (!channel) {
      continue;
    }

    totals.channels += 1;
    const channelTotals = await backfillChannel(channel, storage, config, cutoffMs);
    mergeTotals(totals, channelTotals);
  }

  return totals;
}

async function backfillChannel(channel, storage, config, cutoffMs) {
  const totals = {
    scannedMessages: 0,
    awardedMessages: 0,
    duplicateMessages: 0,
    awardedMessagePoints: 0,
    awardedReactions: 0,
    duplicateReactions: 0,
    awardedReactionPoints: 0,
  };

  let before = null;
  let stop = false;

  while (!stop && totals.scannedMessages < config.backfillMaxMessagesPerChannel) {
    const limit = Math.min(100, config.backfillMaxMessagesPerChannel - totals.scannedMessages);
    const batch = await channel.messages.fetch(before ? { limit, before } : { limit });
    if (batch.size === 0) {
      break;
    }

    const messages = [...batch.values()].sort((left, right) => right.createdTimestamp - left.createdTimestamp);
    before = messages[messages.length - 1].id;

    for (const message of messages) {
      if (message.createdTimestamp < cutoffMs) {
        stop = true;
        continue;
      }

      totals.scannedMessages += 1;
      if (isSubstantiveMessage(message, config)) {
        const result = await storage.awardMessage(
          userLikeFromMemberOrUser(message.member ?? message.author),
          {
            channelId: message.channelId,
            messageId: message.id,
            createdAt: message.createdAt.toISOString(),
            backfilled: true,
          },
          config.scores,
        );
        if (result.duplicate) {
          totals.duplicateMessages += 1;
        }
        if (result.awarded > 0) {
          totals.awardedMessages += 1;
          totals.awardedMessagePoints += result.awarded;
        }
      }

      const reactionTotals = await backfillMentorReactions(message, storage, config);
      mergeTotals(totals, reactionTotals);
    }

    if (batch.size < limit) {
      break;
    }
  }

  return totals;
}

async function backfillMentorReactions(message, storage, config) {
  const totals = {
    awardedReactions: 0,
    duplicateReactions: 0,
    awardedReactionPoints: 0,
  };

  if (!message.guild || !message.author || message.author.bot) {
    return totals;
  }

  for (const reaction of message.reactions.cache.values()) {
    if (!isPositiveReaction(reaction)) {
      continue;
    }

    const reactors = await reaction.users.fetch({ limit: 100 });
    for (const reactor of reactors.values()) {
      if (reactor.bot || reactor.id === message.author.id) {
        continue;
      }

      const member = await message.guild.members.fetch(reactor.id).catch(() => null);
      if (!isMentorOrSupport(member, config)) {
        continue;
      }

      const result = await storage.awardReaction(
        userLikeFromMemberOrUser(message.member ?? message.author),
        {
          channelId: message.channelId,
          messageId: message.id,
          reactorId: reactor.id,
          emoji: reaction.emoji.name,
          createdAt: message.createdAt.toISOString(),
          backfilled: true,
        },
        config.scores,
      );
      if (result.duplicate) {
        totals.duplicateReactions += 1;
      }
      if (result.awarded > 0) {
        totals.awardedReactions += 1;
        totals.awardedReactionPoints += result.awarded;
      }
    }
  }

  return totals;
}

async function fetchTextChannel(client, channelId) {
  try {
    const channel = await client.channels.fetch(channelId);
    if (channel?.isTextBased() && channel.messages) {
      return channel;
    }
  } catch (error) {
    console.error(`Failed to fetch backfill channel ${channelId}:`, error);
  }
  return null;
}

function mergeTotals(target, source) {
  for (const [key, value] of Object.entries(source)) {
    if (typeof value === 'number') {
      target[key] = (target[key] || 0) + value;
    }
  }
}
