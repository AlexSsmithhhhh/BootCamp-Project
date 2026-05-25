import 'dotenv/config';
import {
  Client,
  Events,
  GatewayIntentBits,
  MessageFlags,
  Partials,
  PermissionFlagsBits,
  REST,
  Routes,
  SlashCommandBuilder,
} from 'discord.js';

import { backfillLeaderboardHistory } from './backfill.js';
import { syncAnnouncementPermissions } from './announcement-permissions.js';
import { config } from './config.js';
import {
  createLeaderboardEmbed,
  createPersonalEmbed,
  excludedLeaderboardUserIds,
  isMentorOrSupport,
  isPositiveReaction,
  isStageChannel,
  isSubstantiveMessage,
  isWorkingChannel,
  MY_POINTS_BUTTON_ID,
  updateDashboard,
  userLikeFromMemberOrUser,
} from './leaderboard.js';
import { applyReactionRole, removeReactionRole } from './reaction-roles.js';
import { LeaderboardStorage } from './storage.js';

const storage = new LeaderboardStorage(config.dataPath, config.timeZone);

const intents = [
  GatewayIntentBits.Guilds,
  GatewayIntentBits.GuildMessages,
  GatewayIntentBits.GuildMessageReactions,
  GatewayIntentBits.GuildVoiceStates,
];

if (config.enableMessageContentIntent) {
  intents.push(GatewayIntentBits.MessageContent);
}

const client = new Client({
  intents,
  partials: [Partials.Message, Partials.Channel, Partials.Reaction],
});

const commands = [
  new SlashCommandBuilder()
    .setName('ping')
    .setDescription('Проверить, что Discord-бот работает.'),
  new SlashCommandBuilder()
    .setName('leaderboard')
    .setDescription('Посмотреть текущий рейтинг BootCamp.'),
  new SlashCommandBuilder()
    .setName('my-points')
    .setDescription('Проверить свои баллы BootCamp.'),
  new SlashCommandBuilder()
    .setName('award-points')
    .setDescription('Начислить участнику баллы вручную. Доступно роли Mentor/ментор.')
    .addUserOption((option) => option
      .setName('user')
      .setDescription('Участник, которому начислить баллы.')
      .setRequired(true))
    .addIntegerOption((option) => option
      .setName('points')
      .setDescription('Сколько баллов начислить.')
      .setMinValue(1)
      .setMaxValue(config.manualAwardMaxPoints)
      .setRequired(true))
    .addStringOption((option) => option
      .setName('reason')
      .setDescription('Причина начисления.')
      .setMaxLength(200)
      .setRequired(false)),
  new SlashCommandBuilder()
    .setName('leaderboard-dashboard')
    .setDescription('Создать или обновить закрепляемый dashboard в текущем канале.')
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageGuild),
].map((command) => command.toJSON());

async function registerCommands() {
  const rest = new REST({ version: '10' }).setToken(config.token);
  await rest.put(
    Routes.applicationGuildCommands(config.clientId, config.guildId),
    { body: commands },
  );
}

client.once(Events.ClientReady, async () => {
  console.log(`Bot online: ${client.user.tag} (${client.user.id})`);
  console.log(`Leaderboard data: ${config.dataPath}`);
  console.log(
    `Leaderboard dashboard: channel=${config.dashboardChannelId || 'auto'} message=${config.dashboardMessageId || 'auto'}`,
  );
  console.log(
    `Invite: https://discord.com/oauth2/authorize?client_id=${config.clientId}&permissions=1099780074646&scope=bot%20applications.commands`,
  );
  console.log(
    `Reaction roles: messageIds=${[...config.reactionRoles.messageIds].join(',') || 'auto'} ` +
      `channels=${[...config.reactionRoles.channelIds].join(',') || 'start-here by name'}`,
  );
  console.log(
    `Announcement permissions: enabled=${config.announcementPermissions.enabled} ` +
      `channel=${config.announcementPermissions.channelId || config.announcementPermissions.channelNames.join('|')} ` +
      `roles=${[...config.announcementPermissions.roleIds].join(',') || config.announcementPermissions.roleNames.join('|')}`,
  );

  try {
    const announcementPermissions = await syncAnnouncementPermissions(client, config);
    if (announcementPermissions.updated) {
      console.log(
        'Announcement permissions synced: ' +
          `channel=${announcementPermissions.channelName} roles=${announcementPermissions.roleNames.join(', ')}`,
      );
    } else {
      console.log(`Announcement permissions not synced: ${announcementPermissions.reason}`);
    }
  } catch (error) {
    console.error('Failed to sync announcement permissions:', error);
  }

  try {
    const backfill = await backfillLeaderboardHistory(client, storage, config);
    if (backfill.enabled) {
      console.log(
        'Leaderboard backfill: ' +
          `channels=${backfill.channels} scanned=${backfill.scannedMessages} ` +
          `messagePoints=${backfill.awardedMessagePoints} reactionPoints=${backfill.awardedReactionPoints} ` +
          `duplicates=${backfill.duplicateMessages + backfill.duplicateReactions}`,
      );
    }
  } catch (error) {
    console.error('Failed to backfill leaderboard history:', error);
  }

  const dashboard = await updateDashboard(client, storage, config);
  if (!dashboard.updated) {
    console.log(`Dashboard not updated on startup: ${dashboard.reason}`);
  }

  setInterval(async () => {
    try {
      await updateDashboard(client, storage, config);
    } catch (error) {
      console.error('Failed to update leaderboard dashboard:', error);
    }
  }, config.updateEveryMs).unref();
});

client.on(Events.MessageCreate, async (message) => {
  try {
    if (message.guildId !== config.guildId) {
      return;
    }
    if (!isWorkingChannel(message.channel, config) || !isSubstantiveMessage(message, config)) {
      return;
    }

    const result = await storage.awardMessage(
      userLikeFromMemberOrUser(message.member ?? message.author),
      {
        channelId: message.channelId,
        messageId: message.id,
      },
      config.scores,
    );

    if (result.awarded > 0) {
      console.log(`Awarded message points: user=${message.author.id} points=${result.awarded}`);
    }
  } catch (error) {
    console.error('Failed to process message:', error);
  }
});

client.on(Events.MessageReactionAdd, async (reaction, reactor) => {
  try {
    if (reaction.partial) {
      await reaction.fetch();
    }
    if (reaction.message.partial) {
      await reaction.message.fetch();
    }
    if (!reaction.message.guild || reaction.message.guildId !== config.guildId) {
      return;
    }
    if (reactor.bot || !isPositiveReaction(reaction)) {
      if (!reactor.bot) {
        const roleResult = await applyReactionRole(reaction, reactor, config);
        if (roleResult.handled) {
          if (roleResult.applied) {
            console.log(
              `Applied reaction role: user=${reactor.id} direction=${roleResult.direction} ` +
                `added=${roleResult.addedRoleIds.join(',') || 'none'}`,
            );
          } else {
            console.log(`Reaction role not applied: user=${reactor.id} reason=${roleResult.reason}`);
          }
        }
      }
      return;
    }

    const roleResult = await applyReactionRole(reaction, reactor, config);
    if (roleResult.handled) {
      if (roleResult.applied) {
        console.log(
          `Applied reaction role: user=${reactor.id} direction=${roleResult.direction} ` +
            `added=${roleResult.addedRoleIds.join(',') || 'none'}`,
        );
      } else {
        console.log(`Reaction role not applied: user=${reactor.id} reason=${roleResult.reason}`);
      }
      return;
    }

    const member = await reaction.message.guild.members.fetch(reactor.id);
    if (!isMentorOrSupport(member, config)) {
      return;
    }

    const target = reaction.message.author;
    if (!target || target.bot || target.id === reactor.id) {
      return;
    }

    const result = await storage.awardReaction(
      userLikeFromMemberOrUser(reaction.message.member ?? target),
      {
        channelId: reaction.message.channelId,
        messageId: reaction.message.id,
        reactorId: reactor.id,
        emoji: reaction.emoji.name,
      },
      config.scores,
    );

    if (result.awarded > 0) {
      console.log(`Awarded mentor reaction: user=${target.id} reactor=${reactor.id} points=${result.awarded}`);
    }
  } catch (error) {
    console.error('Failed to process reaction:', error);
  }
});

client.on(Events.MessageReactionRemove, async (reaction, reactor) => {
  try {
    if (reaction.partial) {
      await reaction.fetch();
    }
    if (reaction.message.partial) {
      await reaction.message.fetch();
    }
    if (!reaction.message.guild || reaction.message.guildId !== config.guildId || reactor.bot) {
      return;
    }

    const roleResult = await removeReactionRole(reaction, reactor, config);
    if (roleResult.handled) {
      if (roleResult.removed) {
        console.log(`Removed reaction role: user=${reactor.id} direction=${roleResult.direction}`);
      } else {
        console.log(`Reaction role not removed: user=${reactor.id} reason=${roleResult.reason}`);
      }
    }
  } catch (error) {
    console.error('Failed to process reaction role removal:', error);
  }
});

client.on(Events.VoiceStateUpdate, async (oldState, newState) => {
  try {
    if (newState.guild.id !== config.guildId || newState.member?.user.bot) {
      return;
    }

    const userLike = userLikeFromMemberOrUser(newState.member);
    const oldStage = isStageChannel(oldState.channel);
    const newStage = isStageChannel(newState.channel);

    if (!oldStage && newStage) {
      await storage.startStageSession(userLike, newState.channelId);
      return;
    }

    if (oldStage && (!newStage || oldState.channelId !== newState.channelId)) {
      const result = await storage.finishStageSession(
        userLike,
        {
          oldChannelId: oldState.channelId,
          newChannelId: newState.channelId,
        },
        {
          ...config.scores,
          stageMinMs: config.stageMinMs,
        },
      );
      if (result.awarded > 0) {
        console.log(`Awarded stage points: user=${newState.id} points=${result.awarded}`);
      }
    }

    if (oldStage && newStage && oldState.channelId !== newState.channelId) {
      await storage.startStageSession(userLike, newState.channelId);
    }
  } catch (error) {
    console.error('Failed to process voice state:', error);
  }
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (interaction.guildId !== config.guildId) {
    return;
  }

  try {
    if (interaction.isButton()) {
      if (interaction.customId !== MY_POINTS_BUTTON_ID) {
        return;
      }
      const excludedUserIds = await excludedLeaderboardUserIds(interaction.guild, storage, config);
      await interaction.reply({
        embeds: [createPersonalEmbed(storage, config, interaction.user.id, { excludedUserIds })],
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (!interaction.isChatInputCommand()) {
      return;
    }

    if (interaction.commandName === 'ping') {
      await interaction.reply({
        content: 'Discord-бот работает. Leaderboard активен.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'leaderboard') {
      const excludedUserIds = await excludedLeaderboardUserIds(interaction.guild, storage, config);
      await interaction.reply({
        embeds: [createLeaderboardEmbed(storage, config, { excludedUserIds })],
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'my-points') {
      const excludedUserIds = await excludedLeaderboardUserIds(interaction.guild, storage, config);
      await interaction.reply({
        embeds: [createPersonalEmbed(storage, config, interaction.user.id, { excludedUserIds })],
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'award-points') {
      const issuer = await interaction.guild.members.fetch(interaction.user.id);
      if (!isMentorOrSupport(issuer, config)) {
        await interaction.reply({
          content: 'Эта команда доступна только администраторам и роли Mentor/ментор.',
          flags: MessageFlags.Ephemeral,
        });
        return;
      }

      const targetUser = interaction.options.getUser('user', true);
      const points = interaction.options.getInteger('points', true);
      const reason = interaction.options.getString('reason')?.trim() || 'Без причины';

      if (targetUser.bot) {
        await interaction.reply({
          content: 'Ботам баллы не начисляем.',
          flags: MessageFlags.Ephemeral,
        });
        return;
      }

      const targetMember = await interaction.guild.members.fetch(targetUser.id).catch(() => null);
      const result = await storage.awardManual(
        userLikeFromMemberOrUser(targetMember ?? targetUser),
        {
          awardedBy: interaction.user.id,
          channelId: interaction.channelId,
          reason,
        },
        points,
      );

      await updateDashboard(client, storage, config);
      console.log(
        `Awarded manual points: user=${targetUser.id} issuer=${interaction.user.id} ` +
          `points=${result.awarded} reason=${reason}`,
      );
      await interaction.reply({
        content: `Начислено ${result.awarded} баллов участнику <@${targetUser.id}>. Теперь всего: ${result.totalPoints}.`,
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'leaderboard-dashboard') {
      await interaction.deferReply({ flags: MessageFlags.Ephemeral });
      const result = await updateDashboard(client, storage, config, {
        forceChannelId: interaction.channelId,
      });
      await interaction.editReply(
        result.updated
          ? `Dashboard обновлён и будет дальше обновляться автоматически. Message ID: ${result.messageId}`
          : `Не удалось обновить dashboard: ${result.reason}`,
      );
    }
  } catch (error) {
    console.error('Failed to process interaction:', error);
    const message = 'Не удалось выполнить команду. Я уже записал ошибку в Railway logs.';
    if (interaction.deferred || interaction.replied) {
      await interaction.editReply(message);
    } else {
      await interaction.reply({ content: message, flags: MessageFlags.Ephemeral });
    }
  }
});

async function main() {
  await storage.init();
  if (config.resetOnStartup) {
    const reset = await storage.resetLeaderboardActivity();
    console.log(
      'Leaderboard reset on startup: ' +
        `users=${reset.users} events=${reset.events} ` +
        `awardedMessagesPreserved=${reset.awardedMessages} ` +
        `awardedReactionsPreserved=${reset.awardedReactions}`,
    );
  }
  await registerCommands();
  await client.login(config.token);
}

process.on('SIGTERM', async () => {
  await storage.save();
  client.destroy();
  process.exit(0);
});

process.on('SIGINT', async () => {
  await storage.save();
  client.destroy();
  process.exit(0);
});

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
