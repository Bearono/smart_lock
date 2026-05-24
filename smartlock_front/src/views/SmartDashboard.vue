<template>
  <div class="min-h-screen bg-gray-900 text-white font-sans overflow-hidden selection:bg-indigo-500 selection:text-white">

    <header class="flex justify-between items-center px-8 py-4 bg-gray-800 bg-opacity-60 border-b border-gray-700 backdrop-blur-md fixed w-full z-50">
      <div class="flex items-center gap-3">
        <div class="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.8)] animate-pulse"></div>
        <h1 class="text-xl font-bold tracking-widest text-gray-100">SECURE<span class="text-indigo-500">LINK</span> OS</h1>
      </div>

      <div class="flex items-center gap-3">
        <div class="text-right hidden md:block mr-2">
          <div class="font-mono text-indigo-300 text-lg">{{ currentTime }}</div>
        </div>

        <button @click="openTab('history')" class="flex items-center gap-2 px-4 py-2 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 rounded-lg transition-all text-sm font-medium focus:outline-none">
          <i class="fas fa-history"></i>
          <span>历史记录</span>
        </button>
        <button @click="openTab('devices')" class="flex items-center gap-2 px-4 py-2 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 rounded-lg transition-all text-sm font-medium focus:outline-none">
          <i class="fas fa-mobile-alt"></i>
          <span>设备列表</span>
        </button>
        <button @click="openTab('guest')" class="flex items-center gap-2 px-4 py-2 bg-green-600/20 hover:bg-green-600/40 text-green-300 border border-green-500/30 rounded-lg transition-all text-sm font-medium focus:outline-none">
          <i class="fas fa-users"></i>
          <span>访客管理</span>
        </button>
        <button @click="openTab('mfa')" class="flex items-center gap-2 px-4 py-2 bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-300 border border-yellow-500/30 rounded-lg transition-all text-sm font-medium focus:outline-none">
          <i class="fas fa-shield-alt"></i>
          <span>MFA安全</span>
        </button>
        <button @click="openTab('face')" class="flex items-center gap-2 px-4 py-2 bg-purple-600/20 hover:bg-purple-600/40 text-purple-300 border border-purple-500/30 rounded-lg transition-all text-sm font-medium focus:outline-none">
          <i class="fas fa-face-smile"></i>
          <span>人脸日志</span>
        </button>

        <div class="relative">
          <button @click="toggleNotificationPanel" class="relative p-2 rounded-full hover:bg-gray-700 transition duration-300 focus:outline-none" :class="{'bg-gray-700 text-white': showNotificationPanel, 'text-gray-400': !showNotificationPanel}">
            <i class="fas fa-bell text-xl"></i>
            <span v-if="unreadCount > 0" class="absolute top-0 right-0 w-4 h-4 bg-red-500 text-[10px] font-bold rounded-full flex items-center justify-center animate-bounce">{{ unreadCount }}</span>
          </button>
          <transition name="slide-fade">
            <div v-if="showNotificationPanel" class="absolute right-0 mt-4 w-80 bg-gray-800 border border-gray-600 rounded-xl shadow-2xl z-50 overflow-hidden backdrop-blur-xl">
              <div class="p-3 border-b border-gray-700 flex justify-between items-center bg-gray-900/50">
                <h3 class="text-sm font-bold text-gray-200">通知中心</h3>
                <div class="flex gap-3 text-xs">
                  <span v-if="unreadCount > 0" @click="clearNotifications" class="text-indigo-400 cursor-pointer hover:underline">清除全部</span>
                  <button @click="showNotificationPanel = false" class="text-gray-500 hover:text-white"><i class="fas fa-times"></i></button>
                </div>
              </div>
              <div class="max-h-64 overflow-y-auto custom-scrollbar">
                <div v-if="notifications.length === 0" class="p-6 text-center text-gray-500 text-xs">
                  <i class="fas fa-check-circle text-2xl mb-2 text-green-500/50"></i>
                  <p>暂无新通知</p>
                </div>
                <div v-else>
                  <div v-for="(note, idx) in notifications" :key="idx" class="p-3 border-b border-gray-700 hover:bg-white/5 transition flex items-start gap-3 relative group">
                    <div class="w-2 h-2 mt-1.5 rounded-full flex-shrink-0" :class="note.priority === 'high' ? 'bg-red-500' : 'bg-yellow-500'"></div>
                    <div>
                      <p class="text-sm font-medium text-gray-200">{{ note.title }}</p>
                      <p class="text-xs text-gray-400 mt-1">{{ note.time }}</p>
                    </div>
                    <button @click.stop="removeNotification(idx)" class="absolute right-2 top-2 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition"><i class="fas fa-times"></i></button>
                  </div>
                </div>
              </div>
            </div>
          </transition>
        </div>

        <button @click="logout" class="text-gray-400 hover:text-red-400 transition ml-2" title="退出系统">
          <i class="fas fa-sign-out-alt text-xl"></i>
        </button>
      </div>
    </header>

    <div class="pt-24 px-6 pb-6 grid grid-cols-1 lg:grid-cols-12 gap-6 h-screen">

      <div class="lg:col-span-8 flex flex-col gap-6 h-full overflow-hidden">

        <div class="relative bg-black rounded-2xl overflow-hidden shadow-2xl border border-gray-700 flex-grow group">
          <img :src="videoUrl" class="w-full h-full object-cover opacity-90 transition duration-700 group-hover:scale-105">
          <div class="absolute top-4 left-4 flex gap-2">
            <span class="bg-red-600/90 px-2 py-1 rounded text-xs font-bold animate-pulse flex items-center gap-1">
              <i class="fas fa-circle text-[8px]"></i> LIVE
            </span>
            <span class="bg-gray-800/90 px-2 py-1 rounded text-xs text-gray-300">
              <i class="fas fa-video mr-1"></i> 监控画面
            </span>
          </div>
        </div>

        <div class="h-1/3 bg-gray-800 bg-opacity-40 border border-gray-700 rounded-2xl flex flex-col backdrop-blur-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-gray-700/50 flex justify-between items-center bg-gray-800/50">
            <h3 class="text-sm font-semibold text-gray-200 flex items-center gap-2">
              <i class="fas fa-clipboard-list text-blue-400"></i> 系统访问日志
            </h3>
            <button @click="openTab('history')" class="text-xs px-3 py-1.5 rounded-full bg-gray-700 hover:bg-indigo-600 hover:text-white text-gray-300 transition-colors flex items-center gap-1 border border-gray-600 hover:border-indigo-500">
              <span>查看全部</span><i class="fas fa-arrow-right text-[10px]"></i>
            </button>
          </div>
          <div class="overflow-y-auto custom-scrollbar p-2">
            <table class="w-full text-left text-xs">
              <thead class="text-gray-500 font-medium bg-gray-700/20">
                <tr><th class="p-2 rounded-l">时间</th><th class="p-2">事件类型</th><th class="p-2">详情</th><th class="p-2 rounded-r">操作人</th></tr>
              </thead>
              <tbody class="text-gray-300">
                <tr v-for="(log, index) in recentLogs" :key="index" class="hover:bg-gray-700/30 transition border-b border-gray-700/30 last:border-0">
                  <td class="p-3 font-mono text-blue-300">{{ log.timestamp?.slice(11, 19) }}</td>
                  <td class="p-3"><span :class="getBadgeClass(log.action)" class="px-2 py-0.5 rounded-full text-[10px] border">{{ getActionText(log.action) }}</span></td>
                  <td class="p-3">{{ log.action }}</td>
                  <td class="p-3 text-gray-400">{{ log.username }}</td>
                </tr>
                <tr v-if="recentLogs.length === 0">
                  <td colspan="4" class="p-3 text-center text-gray-500">暂无记录</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="lg:col-span-4 flex flex-col gap-6 h-full pb-2">
        <div class="bg-gray-800 bg-opacity-60 border border-gray-600 rounded-3xl p-6 flex flex-col items-center justify-center relative shadow-2xl h-1/2">
           <div class="absolute top-4 right-4 text-xs text-gray-500">DEVICE_ID: {{ deviceId }}</div>
           <button @click="toggleLock" :disabled="loading" class="relative w-44 h-44 rounded-full border-[6px] flex flex-col items-center justify-center transition-all duration-300 hover:scale-105 active:scale-95 shadow-2xl"
            :class="isLocked ? 'border-gray-700 bg-gradient-to-br from-gray-800 to-gray-900 shadow-[0_0_30px_rgba(0,0,0,0.5)]' : 'border-green-500/50 bg-gray-800 shadow-[0_0_30px_rgba(34,197,94,0.3)]'">
            <i class="fas text-5xl mb-3 transition-colors duration-300" :class="isLocked ? 'fa-lock text-red-500' : 'fa-lock-open text-green-400'"></i>
            <span class="text-sm font-bold tracking-[0.2em]" :class="isLocked ? 'text-red-500' : 'text-green-400'">{{ isLocked ? '已上锁' : '已开启' }}</span>
           </button>
           <p class="mt-6 text-gray-400 text-xs">点击上方按钮切换状态</p>
           <div class="mt-4 flex items-center gap-2 text-xs text-gray-500">
             <i class="fas fa-battery-half"></i> 电量 {{ battery }}%
           </div>
           <div class="mt-2 flex items-center gap-2 text-xs" :class="deviceOnline ? 'text-green-400' : 'text-red-400'">
             <i class="fas fa-wifi"></i> {{ deviceOnline ? '在线' : '离线' }}
           </div>
        </div>

        <div class="bg-gray-800/40 rounded-2xl p-5 border border-gray-700 flex flex-col justify-center gap-3">
          <h3 class="text-sm text-gray-400 mb-1">功能调试</h3>
          <button @click="triggerAlarm" class="w-full py-2 bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50 rounded-lg transition text-sm">
            <i class="fas fa-exclamation-circle mr-2"></i> 模拟入侵报警
          </button>
          <button @click="openTab('alarm')" class="w-full py-2 bg-yellow-600/20 hover:bg-yellow-600/40 text-yellow-400 border border-yellow-600/50 rounded-lg transition text-sm">
             <i class="fas fa-list mr-2"></i> 查看报警记录
          </button>
          <button @click="openMfaDoor" class="w-full py-2 bg-purple-600/20 hover:bg-purple-600/40 text-purple-400 border border-purple-600/50 rounded-lg transition text-sm">
             <i class="fas fa-door-open mr-2"></i> MFA远程开门（测试）
          </button>
        </div>
      </div>
    </div>

    <!-- 通用弹窗 -->
    <transition name="modal">
      <div v-if="currentModal" class="fixed inset-0 z-[100] flex items-center justify-center">
        <div class="absolute inset-0 bg-black bg-opacity-80 backdrop-blur-sm" @click="currentModal = null"></div>
        <div class="relative z-10 bg-gray-800 border border-gray-600 w-11/12 max-w-4xl rounded-2xl shadow-2xl flex flex-col overflow-hidden" :class="currentModal === 'guest' || currentModal === 'mfa' ? 'max-w-xl' : ''">
          <div class="flex justify-between items-center p-6 border-b border-gray-700 bg-gray-800">
            <h2 class="text-xl font-bold text-white"><i :class="modalIcon" class="mr-2"></i>{{ modalTitle }}</h2>
            <button @click="currentModal = null" class="text-gray-400 hover:text-white"><i class="fas fa-times text-lg"></i></button>
          </div>
          <div class="flex-grow overflow-auto p-6 bg-gray-900/50">

            <!-- 历史记录 -->
            <div v-if="currentModal === 'history'">
              <table class="w-full text-left border-collapse">
                <thead><tr class="text-gray-400 border-b border-gray-700 text-sm"><th class="pb-3 pl-2">时间</th><th class="pb-3">事件</th><th class="pb-3">详情</th><th class="pb-3">操作人</th></tr></thead>
                <tbody class="text-gray-300 text-sm">
                  <tr v-for="(log, idx) in allLogs" :key="idx" class="border-b border-gray-800 hover:bg-gray-700/50 transition">
                    <td class="py-3 pl-2 font-mono text-indigo-300">{{ log.timestamp?.slice(0, 19) }}</td>
                    <td class="py-3"><span :class="getBadgeClass(log.action)" class="px-2 py-1 rounded text-xs border">{{ getActionText(log.action) }}</span></td>
                    <td class="py-3">{{ log.action }}</td>
                    <td class="py-3 text-gray-400">{{ log.username }}</td>
                  </tr>
                  <tr v-if="allLogs.length === 0"><td colspan="4" class="py-6 text-center text-gray-500">暂无记录</td></tr>
                </tbody>
              </table>
              <div class="mt-4 flex justify-center gap-2">
                <button @click="loadHistory(currentPage - 1)" :disabled="currentPage <= 1" class="px-3 py-1 bg-gray-700 rounded text-sm disabled:opacity-50">上一页</button>
                <span class="px-3 py-1 text-gray-400 text-sm">第 {{ currentPage }} / {{ totalPages || 1 }} 页</span>
                <button @click="loadHistory(currentPage + 1)" :disabled="currentPage >= totalPages" class="px-3 py-1 bg-gray-700 rounded text-sm disabled:opacity-50">下一页</button>
              </div>
            </div>

            <!-- 设备列表 -->
            <div v-if="currentModal === 'devices'">
              <table class="w-full text-left border-collapse">
                <thead><tr class="text-gray-400 border-b border-gray-700 text-sm"><th class="pb-3 pl-2">设备ID</th><th class="pb-3">状态</th><th class="pb-3">电量</th><th class="pb-3">在线</th><th class="pb-3">最后更新</th></tr></thead>
                <tbody class="text-gray-300 text-sm">
                  <tr v-for="(d, idx) in deviceList" :key="idx" class="border-b border-gray-800 hover:bg-gray-700/50 transition">
                    <td class="py-3 pl-2 font-mono text-indigo-300">{{ d.device_id }}</td>
                    <td class="py-3"><span :class="d.status === 'LOCKED' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-green-500/20 text-green-400 border-green-500/30'" class="px-2 py-1 rounded text-xs border">{{ d.status }}</span></td>
                    <td class="py-3">{{ d.battery }}%</td>
                    <td class="py-3"><span :class="d.is_online ? 'text-green-400' : 'text-red-400'"><i class="fas fa-circle text-[6px] mr-1"></i>{{ d.is_online ? '在线' : '离线' }}</span></td>
                    <td class="py-3 text-gray-400">{{ d.last_update?.slice(0, 19) }}</td>
                  </tr>
                  <tr v-if="deviceList.length === 0"><td colspan="5" class="py-6 text-center text-gray-500">暂无设备</td></tr>
                </tbody>
              </table>
            </div>

            <!-- 访客管理 -->
            <div v-if="currentModal === 'guest'">
              <div class="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
                <h4 class="text-sm font-bold text-gray-200 mb-3"><i class="fas fa-user-plus mr-1 text-green-400"></i>创建访客授权</h4>
                <div class="space-y-3">
                  <input v-model="guestForm.guest_name" type="text" placeholder="访客姓名" class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500 text-sm">
                  <div class="flex gap-3">
                    <input v-model="guestForm.valid_hours" type="number" placeholder="有效期(小时)" class="w-1/2 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm">
                    <input v-model="guestForm.max_uses" type="number" placeholder="最大次数" class="w-1/2 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm">
                  </div>
                  <button @click="createGuest" :disabled="guestLoading" class="w-full py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm transition">
                    {{ guestLoading ? '创建中...' : '创建授权码' }}
                  </button>
                  <div v-if="guestCode" class="p-3 bg-gray-900 rounded text-center">
                    <p class="text-xs text-gray-400 mb-1">访客授权码（仅显示一次）</p>
                    <p class="text-lg font-mono text-green-400 break-all">{{ guestCode }}</p>
                  </div>
                </div>
              </div>
              <h4 class="text-sm font-bold text-gray-200 mb-3">访客授权列表</h4>
              <table class="w-full text-left border-collapse">
                <thead><tr class="text-gray-400 border-b border-gray-700 text-sm"><th class="pb-3 pl-2">访客</th><th class="pb-3">有效期至</th><th class="pb-3">次数</th><th class="pb-3">状态</th><th class="pb-3">操作</th></tr></thead>
                <tbody class="text-gray-300 text-sm">
                  <tr v-for="(g, idx) in guestList" :key="idx" class="border-b border-gray-800 hover:bg-gray-700/50 transition">
                    <td class="py-3 pl-2">{{ g.guest_name }}</td>
                    <td class="py-3 text-gray-400 font-mono">{{ g.valid_until?.slice(0, 19) }}</td>
                    <td class="py-3 text-gray-400">{{ g.used_count }} / {{ g.max_uses }}</td>
                    <td class="py-3"><span :class="g.is_active ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'bg-gray-500/20 text-gray-400 border-gray-500/30'" class="px-2 py-1 rounded text-xs border">{{ g.is_active ? '有效' : '已失效' }}</span></td>
                    <td class="py-3">
                      <button v-if="g.is_active" @click="revokeGuest(g.id)" class="px-2 py-1 bg-red-600/30 text-red-400 rounded text-xs hover:bg-red-600/50">撤销</button>
                    </td>
                  </tr>
                  <tr v-if="guestList.length === 0"><td colspan="5" class="py-6 text-center text-gray-500">暂无访客授权</td></tr>
                </tbody>
              </table>
            </div>

            <!-- MFA安全 -->
            <div v-if="currentModal === 'mfa'">
              <div class="space-y-4">
                <div class="p-4 bg-gray-800 rounded-lg border border-gray-700">
                  <div class="flex justify-between items-center mb-3">
                    <h4 class="text-sm font-bold text-gray-200"><i class="fas fa-key mr-1 text-yellow-400"></i>TOTP 动态口令</h4>
                    <span :class="mfaStatus.totp_bound ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'" class="px-2 py-1 rounded text-xs border">{{ mfaStatus.totp_bound ? '已绑定' : '未绑定' }}</span>
                  </div>
                  <div v-if="!mfaStatus.totp_bound">
                    <button @click="bindTotp" :disabled="mfaLoading" class="w-full py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded text-sm transition">
                      {{ mfaLoading ? '生成中...' : '绑定 TOTP' }}
                    </button>
                    <div v-if="totpSecret" class="mt-3 p-3 bg-gray-900 rounded">
                      <p class="text-xs text-gray-400 mb-1">密钥（请妥善保管）</p>
                      <p class="text-mono text-yellow-400 break-all">{{ totpSecret }}</p>
                      <p class="text-xs text-gray-400 mt-1 mb-2">请使用 Google Authenticator 或其他 TOTP 应用扫描下方二维码</p>
                      <img v-if="totpQrUri" :src="totpQrUri" class="mx-auto border border-gray-600 rounded" alt="TOTP QR">
                    </div>
                    <div v-if="totpSecret" class="mt-3">
                      <input v-model="totpVerifyCode" type="text" maxlength="6" placeholder="输入6位验证码确认绑定" class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500 text-sm text-center tracking-widest">
                      <button @click="verifyTotpBind" :disabled="totpVerifyCode.length !== 6" class="mt-2 w-full py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm transition disabled:opacity-50">
                        确认绑定
                      </button>
                    </div>
                  </div>
                  <div v-else>
                    <button @click="unbindTotp" class="w-full py-2 bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50 rounded text-sm transition">解除绑定</button>
                  </div>
                </div>

                <div class="p-4 bg-gray-800 rounded-lg border border-gray-700">
                  <h4 class="text-sm font-bold text-gray-200 mb-3"><i class="fas fa-mobile-alt mr-1 text-blue-400"></i>已绑定设备</h4>
                  <div v-if="mfaStatus.devices?.length > 0" class="space-y-2">
                    <div v-for="d in mfaStatus.devices" :key="d.credential_id" class="flex justify-between items-center p-2 bg-gray-700/50 rounded">
                      <span class="text-sm text-gray-300"><i class="fas fa-mobile-alt mr-2"></i>{{ d.device_id }}</span>
                      <button @click="unbindDevice(d.device_id)" class="px-2 py-1 bg-red-600/30 text-red-400 rounded text-xs hover:bg-red-600/50">解绑</button>
                    </div>
                  </div>
                  <p v-else class="text-sm text-gray-500">暂无绑定设备</p>
                  <div class="mt-3 flex gap-2">
                    <input v-model="newDeviceId" type="text" placeholder="新设备ID" class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500 text-sm">
                    <button @click="bindDevice" :disabled="!newDeviceId" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm transition disabled:opacity-50">绑定设备</button>
                  </div>
                </div>

                <div class="p-4 bg-gray-800 rounded-lg border border-gray-700">
                  <h4 class="text-sm font-bold text-gray-200 mb-2"><i class="fas fa-door-open mr-1 text-purple-400"></i>MFA开门流程</h4>
                  <div class="text-xs text-gray-400 space-y-1">
                    <p>1. 深夜时段(22:00-06:00)开门需要TOTP验证</p>
                    <p>2. 人脸验证 + 设备验证 为基础因子</p>
                    <p>3. 连续5次验证失败将锁定设备</p>
                  </div>
                  <button @click="openMfaDoor" class="mt-3 w-full py-2 bg-purple-600 hover:bg-purple-500 text-white rounded text-sm transition">
                    发起 MFA 开门请求
                  </button>
                </div>
              </div>
            </div>

            <!-- 人脸日志 -->
            <div v-if="currentModal === 'face'">
              <table class="w-full text-left border-collapse">
                <thead><tr class="text-gray-400 border-b border-gray-700 text-sm"><th class="pb-3 pl-2">时间</th><th class="pb-3">设备</th><th class="pb-3">预期用户</th><th class="pb-3">识别用户</th><th class="pb-3">相似度</th><th class="pb-3">结果</th></tr></thead>
                <tbody class="text-gray-300 text-sm">
                  <tr v-for="(f, idx) in faceLogs" :key="idx" class="border-b border-gray-800 hover:bg-gray-700/50 transition">
                    <td class="py-3 pl-2 font-mono text-indigo-300">{{ f.timestamp?.slice(0, 19) }}</td>
                    <td class="py-3 text-gray-400">{{ f.device_id }}</td>
                    <td class="py-3">{{ f.expected_username }}</td>
                    <td class="py-3">{{ f.face_user_id }}</td>
                    <td class="py-3"><span :class="f.similarity_score >= 0.7 ? 'text-green-400' : 'text-red-400'">{{ (f.similarity_score * 100).toFixed(1) }}%</span></td>
                    <td class="py-3"><span :class="f.passed ? 'bg-green-500/20 text-green-400 border-green-500/30' : 'bg-red-500/20 text-red-400 border-red-500/30'" class="px-2 py-1 rounded text-xs border">{{ f.passed ? '通过' : '失败' }}</span></td>
                  </tr>
                  <tr v-if="faceLogs.length === 0"><td colspan="6" class="py-6 text-center text-gray-500">暂无记录</td></tr>
                </tbody>
              </table>
              <div class="mt-4 flex justify-center gap-2">
                <button @click="loadFaceLogs(facePage - 1)" :disabled="facePage <= 1" class="px-3 py-1 bg-gray-700 rounded text-sm disabled:opacity-50">上一页</button>
                <span class="px-3 py-1 text-gray-400 text-sm">第 {{ facePage }} 页</span>
                <button @click="loadFaceLogs(facePage + 1)" class="px-3 py-1 bg-gray-700 rounded text-sm disabled:opacity-50">下一页</button>
              </div>
            </div>

            <!-- 报警记录 -->
            <div v-if="currentModal === 'alarm'">
              <table class="w-full text-left border-collapse">
                <thead><tr class="text-gray-400 border-b border-gray-700 text-sm"><th class="pb-3 pl-2">时间</th><th class="pb-3">类型</th><th class="pb-3">消息</th><th class="pb-3">截图</th><th class="pb-3">状态</th><th class="pb-3">操作</th></tr></thead>
                <tbody class="text-gray-300 text-sm">
                  <tr v-for="(a, idx) in alarmList" :key="idx" class="border-b border-gray-800 hover:bg-gray-700/50 transition">
                    <td class="py-3 pl-2 font-mono text-indigo-300">{{ a.timestamp?.slice(0, 19) }}</td>
                    <td class="py-3"><span :class="a.status === 'pending' ? 'bg-red-500/20 text-red-400 border-red-500/30' : 'bg-green-500/20 text-green-400 border-green-500/30'" class="px-2 py-1 rounded text-xs border">{{ a.alarm_type }}</span></td>
                    <td class="py-3">{{ a.message }}</td>
                    <td class="py-3">
                      <img v-if="a.snapshot_path && a.snapshot_path !== '无画面'" :src="'http://localhost:5000' + a.snapshot_path" class="h-10 rounded border border-gray-600">
                      <span v-else class="text-gray-500 text-xs">无</span>
                    </td>
                    <td class="py-3 text-gray-400">{{ a.status }}</td>
                    <td class="py-3">
                      <div class="flex gap-1">
                        <button v-if="a.status === 'pending'" @click="resolveAlarm(a.id, 'resolved')" class="px-2 py-1 bg-green-600/30 text-green-400 rounded text-xs hover:bg-green-600/50">已处理</button>
                        <button v-if="a.status === 'pending'" @click="resolveAlarm(a.id, 'ignored')" class="px-2 py-1 bg-gray-600/30 text-gray-400 rounded text-xs hover:bg-gray-600/50">忽略</button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="alarmList.length === 0"><td colspan="6" class="py-6 text-center text-gray-500">暂无记录</td></tr>
                </tbody>
              </table>
            </div>

          </div>
        </div>
      </div>
    </transition>

    <!-- MFA开门弹窗 -->
    <transition name="modal">
      <div v-if="showMfaDoorModal" class="fixed inset-0 z-[100] flex items-center justify-center">
        <div class="absolute inset-0 bg-black bg-opacity-80 backdrop-blur-sm" @click="showMfaDoorModal = false"></div>
        <div class="relative z-10 bg-gray-800 border border-gray-600 w-11/12 max-w-md rounded-2xl shadow-2xl flex flex-col overflow-hidden">
          <div class="flex justify-between items-center p-6 border-b border-gray-700 bg-gray-800">
            <h2 class="text-xl font-bold text-white"><i class="fas fa-door-open mr-2 text-purple-500"></i>MFA 远程开门</h2>
            <button @click="showMfaDoorModal = false" class="text-gray-400 hover:text-white"><i class="fas fa-times text-lg"></i></button>
          </div>
          <div class="p-6 space-y-4">
            <div class="flex items-center gap-2 text-sm">
              <span class="w-6 h-6 rounded-full flex items-center justify-center" :class="mfaStep >= 1 ? 'bg-purple-600' : 'bg-gray-600'">1</span>
              <div class="flex-1 h-0.5" :class="mfaStep >= 2 ? 'bg-purple-600' : 'bg-gray-600'"></div>
              <span class="w-6 h-6 rounded-full flex items-center justify-center" :class="mfaStep >= 2 ? 'bg-purple-600' : 'bg-gray-600'">2</span>
              <div class="flex-1 h-0.5" :class="mfaStep >= 3 ? 'bg-purple-600' : 'bg-gray-600'"></div>
              <span class="w-6 h-6 rounded-full flex items-center justify-center" :class="mfaStep >= 3 ? 'bg-purple-600' : 'bg-gray-600'">3</span>
            </div>
            <p class="text-center text-sm text-gray-400">{{ mfaStep === 1 ? '正在发起开门请求...' : mfaStep === 2 ? '人脸验证中，请稍候...' : '验证完成，正在确认开门...' }}</p>

            <div v-if="mfaStep === 2 && requiresTotp" class="mt-4">
              <p class="text-sm text-yellow-400 mb-2"><i class="fas fa-moon mr-1"></i>深夜模式：需要输入TOTP验证码</p>
              <input v-model="mfaTotpCode" maxlength="6" placeholder="请输入6位验证码" class="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-500 text-sm text-center tracking-widest">
            </div>

            <div v-if="mfaDoorMsg" class="p-3 rounded text-sm text-center" :class="mfaDoorSuccess ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'">
              {{ mfaDoorMsg }}
            </div>

            <div v-if="mfaStep < 3 && !mfaDoorMsg">
              <div v-if="mfaStep === 1" class="text-center py-4">
                <i class="fas fa-spinner fa-spin text-3xl text-purple-400 mb-2"></i>
              </div>
              <button v-if="mfaStep === 2" @click="confirmMfaDoor" :disabled="requiresTotp && mfaTotpCode.length !== 6" class="w-full py-2 bg-purple-600 hover:bg-purple-500 text-white rounded transition disabled:opacity-50">
                {{ requiresTotp && mfaTotpCode.length !== 6 ? '请输入验证码' : '确认开门' }}
              </button>
            </div>
            <button v-if="mfaStep >= 3" @click="showMfaDoorModal = false; resetMfaDoor()" class="w-full py-2 bg-gray-600 hover:bg-gray-500 text-white rounded transition">关闭</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Toast通知 -->
    <div class="fixed top-20 right-6 z-[60] flex flex-col gap-2 pointer-events-none">
      <transition-group name="toast">
        <div v-for="toast in activeToasts" :key="toast.id" class="bg-gray-800 border-l-4 p-4 pr-10 rounded shadow-2xl flex items-center gap-3 min-w-[320px] pointer-events-auto backdrop-blur-md relative" :class="toast.type === 'alarm' ? 'border-red-500 text-red-100' : 'border-blue-500 text-blue-100'">
          <div class="w-8 h-8 rounded-full flex items-center justify-center bg-white/10 flex-shrink-0"><i :class="toast.icon"></i></div>
          <div><h4 class="font-bold text-sm">{{ toast.title }}</h4><p class="text-xs opacity-80 mt-0.5">{{ toast.msg }}</p></div>
          <button @click="closeToast(toast.id)" class="absolute top-2 right-2 text-white/40 hover:text-white transition w-6 h-6 flex items-center justify-center rounded-full hover:bg-white/10"><i class="fas fa-times text-xs"></i></button>
        </div>
      </transition-group>
    </div>

  </div>
</template>

<script>
import { lock, alarm, mfa, device, face } from '../api/index'

export default {
  name: 'SmartDashboard',
  data() {
    return {
      isLocked: true,
      loading: false,
      currentTime: '',
      deviceId: 'door_01',
      battery: 90,
      deviceOnline: false,
      videoUrl: 'http://localhost:5000/video_feed',
      showNotificationPanel: false,
      notifications: [],
      activeToasts: [],
      recentLogs: [],
      allLogs: [],
      currentPage: 1,
      totalPages: 1,
      alarmList: [],
      deviceList: [],
      guestList: [],
      faceLogs: [],
      facePage: 1,
      currentModal: null,
      modalTitle: '',
      modalIcon: '',
      showGuestModal: false,
      guestForm: { guest_name: '', valid_hours: 24, max_uses: 1 },
      guestCode: '',
      guestLoading: false,
      mfaStatus: { totp_bound: false, devices: [] },
      mfaLoading: false,
      totpSecret: '',
      totpQrUri: '',
      totpVerifyCode: '',
      newDeviceId: '',
      showMfaDoorModal: false,
      mfaStep: 0,
      mfaRequestId: '',
      mfaNonce: '',
      requiresFace: false,
      requiresTotp: false,
      mfaTotpCode: '',
      mfaDoorMsg: '',
      mfaDoorSuccess: false
    };
  },
  computed: {
    unreadCount() { return this.notifications.length }
  },
  async mounted() {
    this.updateTime()
    setInterval(this.updateTime, 1000)
    await this.fetchLockStatus()
    await this.fetchDevices()
    await this.fetchHistory(1)
    await this.fetchAlarms()
    await this.fetchMfaStatus()
    setInterval(() => { this.fetchAlarms(); this.fetchDevices() }, 15000)
  },
  methods: {
    updateTime() { this.currentTime = new Date().toLocaleTimeString('zh-CN', { hour12: false }) },

    openTab(tab) {
      const map = {
        history: { title: '完整历史日志', icon: 'fas fa-database text-indigo-500' },
        devices: { title: '设备列表', icon: 'fas fa-mobile-alt text-blue-400' },
        guest: { title: '访客管理', icon: 'fas fa-users text-green-400' },
        mfa: { title: 'MFA 安全设置', icon: 'fas fa-shield-alt text-yellow-400' },
        face: { title: '人脸识别日志', icon: 'fas fa-face-smile text-purple-400' },
        alarm: { title: '报警记录', icon: 'fas fa-exclamation-triangle text-red-500' }
      }
      this.modalTitle = map[tab].title
      this.modalIcon = map[tab].icon
      this.currentModal = tab
      if (tab === 'history') { this.loadHistory(1) }
      else if (tab === 'devices') { this.fetchDevices() }
      else if (tab === 'guest') { this.fetchGuestList() }
      else if (tab === 'mfa') { this.fetchMfaStatus() }
      else if (tab === 'face') { this.loadFaceLogs(1) }
      else if (tab === 'alarm') { this.fetchAlarms() }
    },

    async toggleLock() {
      if (this.loading) return
      this.loading = true
      try {
        const action = this.isLocked ? 'UNLOCK' : 'LOCK'
        await lock.control(action, this.deviceId)
        this.isLocked = !this.isLocked
        this.showToast('门锁状态更新', this.isLocked ? '已锁定' : '已解锁', 'access')
        await this.fetchHistory(1)
      } catch (error) {
        this.showToast('操作失败', error.response?.data?.msg || '网络错误', 'alarm')
      } finally {
        this.loading = false
      }
    },
    async fetchLockStatus() {
      try {
        const res = await lock.getStatus(this.deviceId)
        this.isLocked = res.data.status === 'LOCKED'
        this.battery = res.data.battery || 90
        this.deviceOnline = true
      } catch { this.deviceOnline = false }
    },
    async fetchHistory(page = 1) {
      try {
        const res = await lock.getHistory(page, 10)
        if (page === 1) this.allLogs = res.data.data || []
        else this.allLogs = [...this.allLogs, ...(res.data.data || [])]
        this.recentLogs = this.allLogs.slice(0, 5)
        this.currentPage = res.data.current_page
        this.totalPages = res.data.pages
      } catch (error) { console.error('获取历史记录失败', error) }
    },
    loadHistory(page) { this.fetchHistory(page) },

    async fetchDevices() {
      try {
        const res = await device.getStatus()
        this.deviceList = Array.isArray(res.data) ? res.data : [res.data]
      } catch (error) { console.error('获取设备列表失败', error) }
    },

    async fetchAlarms() {
      try {
        const res = await alarm.list(null, 20)
        this.alarmList = res.data || []
        this.alarmList.forEach(a => {
          if (a.status === 'pending') {
            const exists = this.notifications.find(n => n.title === a.alarm_type)
            if (!exists) this.notifications.unshift({ title: a.alarm_type, time: '刚刚', priority: 'high' })
          }
        })
      } catch (error) { console.error('获取报警记录失败', error) }
    },
    async resolveAlarm(alarmId, status) {
      try {
        await alarm.update(alarmId, status)
        this.showToast('处理成功', `报警已标记为${status}`, 'access')
        await this.fetchAlarms()
      } catch (error) { console.error('处理报警失败', error) }
    },
    async triggerAlarm() {
      try {
        await alarm.trigger('入侵报警', '测试报警触发')
        this.showToast('报警已触发', '入侵报警已发送', 'alarm')
        await this.fetchAlarms()
      } catch (error) { this.showToast('触发失败', error.response?.data?.msg || '网络错误', 'alarm') }
    },

    async fetchGuestList() {
      try { const res = await mfa.listGuest(); this.guestList = res.data || [] } catch (error) { console.error('获取访客列表失败', error) }
    },
    async createGuest() {
      if (!this.guestForm.guest_name) { alert('请输入访客姓名'); return }
      this.guestLoading = true
      try {
        const res = await mfa.createGuest(this.guestForm.guest_name, this.guestForm.valid_hours, this.guestForm.max_uses)
        this.guestCode = res.data.pass_code
        this.showToast('创建成功', `访客 ${this.guestForm.guest_name} 的授权码已生成`, 'access')
        await this.fetchGuestList()
      } catch (error) { this.showToast('创建失败', error.response?.data?.msg || '网络错误', 'alarm') }
      finally { this.guestLoading = false }
    },
    async revokeGuest(passId) {
      try { await mfa.revokeGuest(passId); this.showToast('撤销成功', '访客授权已撤销', 'access'); await this.fetchGuestList() } catch (error) { console.error('撤销失败', error) }
    },

    async fetchMfaStatus() {
      try { const res = await mfa.getStatus(); this.mfaStatus = res.data } catch (error) { console.error('获取MFA状态失败', error) }
    },
    async bindTotp() {
      this.mfaLoading = true
      try {
        const res = await mfa.bindTotp()
        this.totpSecret = res.data.secret
        this.totpQrUri = `https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=${encodeURIComponent(res.data.qr_uri)}`
        this.mfaCredentialId = res.data.credential_id
        this.showToast('密钥已生成', '请扫描二维码或输入密钥绑定TOTP', 'access')
      } catch (error) { this.showToast('生成失败', error.response?.data?.msg || '网络错误', 'alarm') }
      finally { this.mfaLoading = false }
    },
    async verifyTotpBind() {
      if (!this.totpVerifyCode || this.totpVerifyCode.length !== 6) return
      try {
        await mfa.verifyTotp(this.totpVerifyCode, this.mfaCredentialId)
        this.showToast('绑定成功', 'TOTP已成功绑定', 'access')
        this.totpSecret = ''; this.totpQrUri = ''; this.totpVerifyCode = ''
        await this.fetchMfaStatus()
      } catch (error) { this.showToast('验证失败', '验证码错误', 'alarm') }
    },
    async unbindTotp() {
      try { await mfa.unbindTotp(); this.showToast('已解绑', 'TOTP绑定已解除', 'access'); await this.fetchMfaStatus() } catch (error) { console.error('解绑失败', error) }
    },
    async bindDevice() {
      if (!this.newDeviceId) return
      try { await mfa.bindDevice(this.newDeviceId); this.showToast('绑定成功', `设备 ${this.newDeviceId} 已绑定`, 'access'); this.newDeviceId = ''; await this.fetchMfaStatus() } catch (error) { this.showToast('绑定失败', error.response?.data?.msg || '网络错误', 'alarm') }
    },
    async unbindDevice(deviceId) {
      try { await mfa.unbindDevice(deviceId); this.showToast('已解绑', `设备 ${deviceId} 已解绑`, 'access'); await this.fetchMfaStatus() } catch (error) { console.error('解绑失败', error) }
    },

    async openMfaDoor() {
      this.showMfaDoorModal = true
      this.mfaStep = 1; this.mfaDoorMsg = ''; this.mfaDoorSuccess = false; this.mfaTotpCode = ''
      try {
        const res = await mfa.openDoorRequest(this.deviceId)
        this.mfaRequestId = res.data.request_id; this.mfaNonce = res.data.nonce
        this.requiresFace = res.data.requires_face; this.requiresTotp = res.data.requires_totp
        this.mfaStep = 2
      } catch (error) { this.mfaDoorMsg = error.response?.data?.msg || '开门请求失败'; this.mfaStep = 0 }
    },
    async confirmMfaDoor() {
      this.mfaStep = 3
      try {
        const res = await mfa.openDoorConfirm(this.mfaRequestId, this.requiresTotp ? this.mfaTotpCode : undefined)
        this.mfaDoorSuccess = true; this.mfaDoorMsg = `开门成功！令牌有效期${res.data.expires_in}秒`
        this.isLocked = false
        this.showToast('MFA开门成功', `令牌有效期${res.data.expires_in}秒`, 'access')
        await this.fetchHistory(1)
      } catch (error) { this.mfaDoorSuccess = false; this.mfaDoorMsg = error.response?.data?.msg || '开门失败' }
    },
    resetMfaDoor() { this.mfaStep = 0; this.mfaRequestId = ''; this.mfaNonce = ''; this.mfaTotpCode = ''; this.mfaDoorMsg = '' },

    async loadFaceLogs(page = 1) {
      try { const res = await face.getLogs(page, 15); this.faceLogs = res.data.data || []; this.facePage = res.data.current_page } catch (error) { console.error('获取人脸日志失败', error) }
    },

    showToast(title, msg, type) {
      const id = Date.now()
      this.activeToasts.push({ id, title, msg, type, icon: type === 'alarm' ? 'fas fa-exclamation-triangle' : 'fas fa-check-circle' })
      setTimeout(() => this.closeToast(id), 4000)
    },
    closeToast(id) { this.activeToasts = this.activeToasts.filter(t => t.id !== id) },
    toggleNotificationPanel() { this.showNotificationPanel = !this.showNotificationPanel },
    clearNotifications() { this.notifications = []; this.showNotificationPanel = false },
    removeNotification(index) { this.notifications.splice(index, 1) },
    logout() {
      if (confirm('确定退出系统?')) { localStorage.removeItem('token'); localStorage.removeItem('username'); this.$router.push('/') }
    },
    getBadgeClass(action) {
      if (action?.includes('报警') || action?.includes('警告')) return 'bg-red-500/20 text-red-400 border-red-500/30'
      if (action?.includes('解锁') || action?.includes('开锁') || action?.includes('UNLOCK')) return 'bg-green-500/20 text-green-400 border-green-500/30'
      if (action?.includes('访客')) return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
      return 'bg-gray-500/20 text-gray-400 border-gray-500/30'
    },
    getActionText(action) {
      if (action?.includes('解锁') || action?.includes('开锁')) return '访问'
      if (action?.includes('报警') || action?.includes('警告')) return '警告'
      if (action?.includes('锁定')) return '系统'
      return '消息'
    }
  }
}
</script>

<style scoped>
.custom-scrollbar::-webkit-scrollbar { width: 4px; }
.custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 4px; }
.slide-fade-enter-active, .slide-fade-leave-active { transition: all 0.2s ease; }
.slide-fade-enter, .slide-fade-leave-to { transform: translateY(-10px); opacity: 0; }
.toast-enter-active, .toast-leave-active { transition: all 0.4s ease; }
.toast-enter { transform: translateX(100%); opacity: 0; }
.toast-leave-to { transform: translateX(100%); opacity: 0; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.3s; }
.modal-enter, .modal-leave-to { opacity: 0; }
</style>