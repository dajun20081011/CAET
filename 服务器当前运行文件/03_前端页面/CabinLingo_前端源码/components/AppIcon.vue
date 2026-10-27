<template>
  <component :is="icons[name] || Document" class="app-icon" aria-hidden="true" />
</template>

<script setup lang="ts">
import {
  ArrowLeft,
  ArrowRight,
  Bell,
  Briefcase,
  ChatDotRound,
  CircleCheck,
  Clock,
  Collection,
  Connection,
  DataAnalysis,
  DataLine,
  Document,
  EditPen,
  Files,
  FolderOpened,
  Headset,
  House,
  Lock,
  MagicStick,
  Management,
  Microphone,
  OfficeBuilding,
  Reading,
  Setting,
  Tickets,
  Tools,
  TrendCharts,
  UploadFilled,
  User,
  UserFilled,
  VideoPlay,
  View,
  Location,
} from '@element-plus/icons-vue'
import type { Component } from 'vue'

defineProps<{ name: string }>()

const icons: Record<string, Component> = {
  back: ArrowLeft,
  right: ArrowRight,
  bell: Bell,
  briefcase: Briefcase,
  chat: ChatDotRound,
  check: CircleCheck,
  clock: Clock,
  collection: Collection,
  connection: Connection,
  dashboard: DataAnalysis,
  trend: DataLine,
  document: Document,
  edit: EditPen,
  files: Files,
  folder: FolderOpened,
  home: House,
  lock: Lock,
  ai: MagicStick,
  management: Management,
  microphone: Microphone,
  headset: Headset,
  tools: Tools,
  location: Location,
  organization: OfficeBuilding,
  course: Reading,
  settings: Setting,
  tasks: Tickets,
  growth: TrendCharts,
  upload: UploadFilled,
  user: User,
  users: UserFilled,
  play: VideoPlay,
  view: View,
}
</script>

<style scoped>
.app-icon{width:1em;height:1em;display:block;flex:none}
</style>
