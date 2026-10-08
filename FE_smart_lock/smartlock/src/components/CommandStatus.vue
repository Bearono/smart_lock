<template>
  <section
    class="command-status"
    :class="`command-status--${status}`"
    role="status"
    aria-live="polite"
  >
    <div v-if="status === 'pending'" class="loading-line" />
    <div class="command-result">
      <p>{{ labels[status] }}</p>
      <small class="mono">命令 ID：{{ commandId }}</small>
      <button v-if="status === 'unknown'" class="button button--small" type="button" @click="start">
        查询原命令结果
      </button>
    </div>
  </section>
</template>

<script>
import { lock } from '../api/index'
import { commandLabels, normalizeCommandStatus } from '../api/commandStatus'

export default {
  name: 'CommandStatus',
  props: {
    commandId: { type: String, required: true },
    credential: { type: Object, default: null }
  },
  emits: ['settled'],
  data: () => ({ status: 'pending', labels: commandLabels, timer: null, generation: 0 }),
  watch: { commandId: 'start' },
  mounted() {
    this.start()
  },
  beforeUnmount() {
    this.generation++
    clearTimeout(this.timer)
  },
  methods: {
    start() {
      clearTimeout(this.timer)
      const generation = ++this.generation
      const deadline = Date.now() + 45000
      this.status = 'pending'
      const poll = async () => {
        let status = 'unknown'
        try {
          const response = this.credential
            ? await lock.getTokenCommand(this.credential.unlock_token, this.credential.device_id)
            : await lock.getCommand(this.commandId)
          status = normalizeCommandStatus(response.data)
        } catch {
          /* Keep querying until the bounded observation window ends. */
        }
        if (generation !== this.generation) return
        if (status === 'pending' || status === 'unknown') {
          if (Date.now() < deadline) {
            this.timer = setTimeout(poll, 1500)
            return
          }
          status = 'unknown'
        }
        this.status = status
        this.$emit('settled', status)
      }
      poll()
    }
  }
}
</script>

<style scoped>
.command-status {
  margin: 0 0 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: #f7f9fc;
}
.command-result {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.command-result p {
  font-weight: 550;
}
.command-status--executed {
  background: #eff9f3;
  border-color: #c6e8d3;
}
.command-status--executed p {
  color: var(--success);
}
.command-status--failed,
.command-status--revoked {
  background: #fff4f4;
  border-color: #f0ccd0;
}
.command-status--failed p,
.command-status--revoked p {
  color: var(--danger);
}
.command-status--unknown,
.command-status--expired {
  background: #fffaef;
  border-color: #efdfb7;
}
small {
  color: var(--muted);
}
small {
  overflow-wrap: anywhere;
}
</style>
