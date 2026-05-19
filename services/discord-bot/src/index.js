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

import { config } from './config.js';
import {
  createLeaderboardEmbed,
  createPersonalEmbed,
  isMentorOrSupport,
  isPositiveReaction,
  isStageChannel,
  isSubstantiveMessage,
  isWorkingChannel,
  updateDashboard,
  userLikeFromMemberOrUser,
} from './leaderboard.js';
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
    `Invite: https://discord.com/oauth2/authorize?client_id=${config.clientId}&permissions=1099780074646&scope=bot%20applications.commands`,
  );

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
  if (!interaction.isChatInputCommand() || interaction.guildId !== config.guildId) {
    return;
  }

  try {
    if (interaction.commandName === 'ping') {
      await interaction.reply({
        content: 'Discord-бот работает. Leaderboard активен.',
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'leaderboard') {
      await interaction.reply({
        embeds: [createLeaderboardEmbed(storage, config)],
        flags: MessageFlags.Ephemeral,
      });
      return;
    }

    if (interaction.commandName === 'my-points') {
      await interaction.reply({
        embeds: [createPersonalEmbed(storage, config, interaction.user.id)],
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
