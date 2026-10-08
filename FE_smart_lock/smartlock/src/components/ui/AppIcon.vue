<script setup>
defineProps({ name: { type: String, default: 'doors' }, size: { type: Number, default: 20 } })
const paths = {
  doors: 'M4 21h16M7 21V4l10-2v19M13 12h.01',
  records: 'M8 3H5v18h14V3h-3M9 2h6v4H9zM8 11h8M8 15h6',
  guests:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M20 8v6M17 11h6',
  alarms: 'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  users:
    'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M17 4a4 4 0 0 1 0 7M23 21v-2a4 4 0 0 0-3-3.87',
  shield: 'M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6zM8 12l3 3 5-6',
  refresh: 'M20 7a9 9 0 1 0 1 8M20 2v5h-5',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  lock: 'M5 10h14v12H5zM8 10V6a4 4 0 0 1 8 0v4M12 15v3',
  camera: 'M3 6h18v14H3zM8 6l2-3h4l2 3M12 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  check: 'M5 12l4 4L19 6',
  close: 'M6 6l12 12M6 18 18 6',
  menu: 'M3 6h18M3 12h18M3 18h18',
  logout: 'M9 3H3v18h6M10 12h11M17 8l4 4-4 4',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14M15 15l6 6',
  copy: 'M9 9h12v12H9zM15 9V3H3v12h6',
  info: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 11v6M12 7h.01'
}
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.doors" />
  </svg>
</template>
