<script setup lang="ts">
import { onMounted } from 'vue'
import type { Evidence } from '../../shared/api/records'
import { admin } from '../../shared/api/index.ts'
import { useResource } from '../../shared/lib/useResource.ts'
import PageHeading from '../../shared/ui/PageHeading.vue'
import InlineNotice from '../../shared/ui/InlineNotice.vue'
const resource = useResource<Evidence | null>(admin.evidence, null)
const { data, loading, error } = resource
function refresh() {
  return resource.load()
}
onMounted(refresh)
</script>
<template>
  <PageHeading
    eyebrow="工程证据"
    title="安心背后的机制"
    description="读取服务当前的真实配置与存储事实，帮助说明家门安全链路。"
  >
    <button class="button" :disabled="loading" @click="refresh">刷新事实</button>
  </PageHeading>
  <InlineNotice v-if="error" tone="warning">{{ error }}</InlineNotice>
  <div v-if="data" class="stack">
    <section class="panel">
      <div class="panel-head"><h3>离线软件验收报告</h3></div>
      <div v-if="data.verification" class="panel-body stack">
        <p>{{ data.verification.passed ? '所列软件检查已通过' : '报告包含未通过检查' }}</p>
        <dl class="detail-list">
          <dt>生成时间</dt>
          <dd>{{ data.verification.created_at }}</dd>
          <dt>环境</dt>
          <dd>{{ data.verification.environment }}</dd>
          <dt>Git 基线</dt>
          <dd class="mono">{{ data.verification.git_sha }}</dd>
          <dt>源码摘要</dt>
          <dd class="mono">{{ data.verification.source_digest }}</dd>
          <dt>验证范围</dt>
          <dd>{{ data.verification.scope }}</dd>
        </dl>
        <p v-for="check in data.verification.checks" :key="check.name">
          {{ check.name }} · {{ check.exit_code === 0 ? '通过' : '未通过' }}
        </p>
        <p class="subtext">报告说明生成时的源码与环境，不代替当前设备状态或实机验收。</p>
      </div>
      <p v-else class="panel-body subtext">
        尚未提供离线验收报告。由维护人员运行 deploy/verify.py 后加载，网页不执行测试命令。
      </p>
    </section>
    <section class="panel">
      <div class="panel-head">
        <h3>通信协议</h3>
        <span class="badge">{{ data.protocol.version }}</span>
      </div>
      <dl class="panel-body detail-list">
        <dt>密钥协商</dt>
        <dd>{{ data.protocol.handshake }}</dd>
        <dt>消息保护</dt>
        <dd>{{ data.protocol.envelope }}</dd>
        <dt>历史上传</dt>
        <dd>{{ data.protocol.legacy_upload_enabled ? '已开启' : '关闭' }}</dd>
        <dt>观察时间</dt>
        <dd>{{ data.observed_at }}</dd>
      </dl>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>从身份到执行</h3></div>
      <div class="panel-body stack">
        <article v-for="item in data.controls" :key="item.name">
          <h3>{{ item.name }}</h3>
          <p class="subtext">{{ item.detail }}</p>
        </article>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>数据库记录数量</h3></div>
      <div class="panel-body">
        <p>
          会话 {{ data.storage.sessions }} · 防重放凭据 {{ data.storage.receipts }} · 命令
          {{ data.storage.commands }}
        </p>
        <p class="subtext">数量包含历史或过期记录，不能解读为在线设备数、攻击数或安全评分。</p>
      </div>
    </section>
    <InlineNotice tone="warning">
      <ul>
        <li v-for="item in data.limitations" :key="item">{{ item }}</li>
      </ul>
    </InlineNotice>
  </div>
  <p v-else-if="loading" role="status">正在读取安全事实…</p>
</template>
