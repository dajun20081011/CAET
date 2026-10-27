<template>
  <main class="admin-mobile">
    <section v-if="activeTab === 'dashboard'" class="mobile-page">
      <MobileHeader title="管理驾驶舱" subtitle="本周仅为统计观察范围 · 计划进度按全周期累计" />
      <FilterTrigger :label="weekLabel" @click="calendarOpen = true" />
      <FilterTrigger :label="selectedPlanLabel" @click="planPickerOpen = true" />

      <section v-if="dashboardLoading" class="mobile-skeleton" aria-label="正在加载驾驶舱">
        <Skeleton width="100%" height="102px" animated />
        <Skeleton width="100%" height="70px" animated />
        <Skeleton width="100%" height="250px" animated />
      </section>
      <template v-else>
        <button class="hero-card" type="button" @click="planPickerOpen = true">
          <span>最终达标率</span>
          <strong>{{ currentStats.finalRate }}%</strong>
          <small>{{ currentStats.passed }} / {{ currentStats.total }} 已达标 · 提交完成 {{ currentStats.submitted }} / {{ currentStats.total }}（{{ currentStats.submissionRate }}%）</small>
          <CircleProgress class="hero-ring" :progress="currentStats.finalRate" :radius="34" :stroke-width="7" color="#ffffff" path-color="#1354c7">
            <b>{{ currentStats.finalRate }}%</b>
          </CircleProgress>
        </button>

        <div class="state-grid" aria-label="互斥状态统计">
          <button type="button" class="state-card success" @click="openLearners('passed')"><span>已达标</span><strong>{{ currentStats.passed }}</strong><small>查看 ›</small></button>
          <button type="button" class="state-card warning" @click="openLearners('pending')"><span>待复核</span><strong>{{ currentStats.pending }}</strong><small>查看 ›</small></button>
          <button type="button" class="state-card danger" @click="openLearners('not-passed')"><span>未达标</span><strong>{{ currentStats.notPassed }}</strong><small>查看 ›</small></button>
        </div>

        <section class="mobile-card plans-card">
          <div class="card-heading"><div><h2>进行中的训练计划</h2><p>默认展示全部计划，可切换指定计划</p></div></div>
          <button v-for="task in visiblePlans" :key="task.id" type="button" class="plan-row" @click="openPlanDetail(task)">
            <span><strong>{{ task.title }}</strong><small>{{ taskItemLabel(task) }} · {{ task.assignment_count }}人</small></span>
            <span class="plan-progress"><b>{{ task.completed_count }}/{{ task.assignment_count }} 达标</b><em>{{ taskRate(task) }}%</em><Progress :percentage="taskRate(task)" :show-text="false" :stroke-width="4" stroke-color="#1463f2" /></span>
          </button>
          <Empty v-if="!visiblePlans.length" description="当前筛选范围没有进行中的训练计划" />
        </section>

        <section class="mobile-card todo-card">
          <div class="card-heading"><div><h2>当前待办</h2></div></div>
          <div class="todo-actions"><button type="button" class="warning" @click="openReviewQueue">{{ currentStats.pending }} 项待复核</button><button type="button" class="danger" @click="openLearners('not-passed')">{{ currentStats.notPassed }} 名/份未达标</button></div>
          <p>状态互斥：已达标 {{ currentStats.passed }}｜待复核 {{ currentStats.pending }}｜未达标 {{ currentStats.notPassed }}；待复核计入提交完成率</p>
        </section>
      </template>
    </section>

    <section v-else-if="activeTab === 'ranking'" class="mobile-page">
      <MobileHeader title="学习排名" subtitle="综合榜为试算排名 · 权重由后台配置" />
      <FilterTrigger :label="weekLabel" @click="calendarOpen = true" />
      <Tabs v-model="rankingTab" class="ranking-tabs">
        <TabPane title="综合试算"><RankingEmpty /></TabPane>
        <TabPane title="完成效率"><RankingEmpty /></TabPane>
        <TabPane title="学习质量"><RankingEmpty /></TabPane>
        <TabPane title="连续达标"><RankingEmpty /></TabPane>
      </Tabs>
      <p class="ranking-note">试算分仅用于当前筛选范围内比较，不作为正式考核成绩；页面不内置固定权重。</p>
    </section>

    <section v-else-if="activeTab === 'learners'" class="mobile-page">
      <MobileHeader title="学员" subtitle="查看当前统计范围与训练计划的完成、复核状态" />
      <FilterTrigger :label="weekLabel" @click="calendarOpen = true" />
      <Searchbar v-model="learnerSearch" class="mobile-search" placeholder="搜索姓名 / 工号" />
      <button class="filter-bar" type="button" @click="learnerFilterOpen = true">
        <span>{{ groupFilter }}</span><span>{{ statusFilterLabel }}</span><span>{{ planFilterLabel }}</span>
      </button>
      <div class="learner-metrics"><span><strong>{{ selectedPlanId === 'all' ? store.learnerUsers.length : currentStats.total }}</strong><small>总数</small></span><span class="success"><strong>{{ currentStats.passed }}</strong><small>达标</small></span><span class="warning"><strong>{{ currentStats.pending }}</strong><small>待复核</small></span><span class="danger"><strong>{{ currentStats.notPassed }}</strong><small>未达标</small></span></div>
      <section v-if="currentTaskRosterLoading" class="mobile-skeleton" aria-label="正在加载任务人员名单"><Skeleton width="100%" height="186px" animated /></section>
      <section v-else-if="currentTaskRosterError" class="learner-progress-feedback" role="alert"><strong>名单读取失败</strong><p>{{ currentTaskRosterError }}</p><button type="button" @click="retryCurrentTaskRoster">重新加载</button></section>
      <section v-else class="mobile-card learner-list">
        <button v-for="user in filteredLearners" :key="user.id" type="button" @click="openLearner(user)">
          <i>{{ initial(user.display_name) }}</i><span><strong>{{ user.display_name }}</strong><small>{{ learnerSubline(user) }}</small></span><em :class="learnerState(user).tone">{{ learnerState(user).label }}</em>
        </button>
        <Empty v-if="!filteredLearners.length" description="当前搜索或筛选条件下没有学员" />
      </section>
    </section>

    <section v-else-if="activeTab === 'plans'" class="mobile-page">
      <MobileHeader title="训练计划" subtitle="计划进度按全周期累计 · 观察范围只限定统计窗口" />
      <FilterTrigger :label="weekLabel" @click="calendarOpen = true" />
      <section class="plan-hero"><span>进行中计划</span><strong>{{ store.activeTasks.length }} 项</strong><small>覆盖 {{ store.totalAssignments }} 人次 · 支持不同截止时间</small><b>已发布</b></section>
      <section class="mobile-card plan-list">
        <article v-for="task in mobilePlans" :key="task.id" :class="{ paused: task.status === 'closed' }">
          <button type="button" @click="openPlanDetail(task)"><span><strong>{{ task.title }}</strong><small>{{ taskItemLabel(task) }} · {{ task.assignment_count }}人 · {{ dueLabel(task) }}</small></span><em>{{ taskRate(task) }}%</em></button>
          <Progress :percentage="taskRate(task)" :show-text="false" :stroke-width="4" stroke-color="#1463f2" />
          <p>完成 {{ task.completed_count }} · 未完成 {{ Math.max(task.assignment_count - task.completed_count, 0) }}<b v-if="task.status === 'closed'">已暂停</b><button type="button" @click="openPlanDetail(task)">详情 ›</button></p>
        </article>
        <Empty v-if="!mobilePlans.length" description="当前没有可管理的训练计划" />
        <p class="plan-rule">任务数量不固定；进入计划后查看具体练习项与人员进度</p>
      </section>
    </section>

    <section v-else class="mobile-page review-page">
      <header class="review-header"><button type="button" aria-label="返回驾驶舱" @click="goTab('dashboard')">‹</button><MobileHeader title="复核队列" subtitle="驾驶舱二级页 · 只处理已提交、等待人工确认的任务" /></header>
      <FilterTrigger :label="weekLabel" @click="calendarOpen = true" />
      <Searchbar v-model="reviewSearch" class="mobile-search" placeholder="搜索学员 / 广播词" />
      <button class="filter-bar" type="button" @click="reviewFilterOpen = true"><span>{{ groupFilter }}</span><span>全部任务</span><span>{{ reviewPriority ? 'AI异常优先' : '默认顺序' }}</span></button>
      <section class="mobile-card review-summary"><span>待复核<strong>{{ filteredReviews.length }}</strong></span><p>优先处理可能影响当前计划质量判定的录音</p></section>
      <section class="mobile-card review-list">
        <button v-for="item in filteredReviews" :key="item.key" type="button" @click="openReview(item)">
          <i>{{ initial(item.learnerName) }}</i><span><strong>{{ item.learnerName }}</strong><small>{{ item.taskTitle }} · {{ timeLabel(item.submittedAt) }}</small></span><em>{{ aiStatusLabel(item.aiStatus) }}<b>待复核</b></em><u>›</u>
        </button>
        <Empty v-if="!filteredReviews.length" :description="store.reviewAvailable ? '当前筛选范围没有待复核任务' : '当前账号没有复核读取权限'" />
      </section>
      <p class="review-entry">入口：驾驶舱 → 当前待办 → 待复核</p>
    </section>

    <p v-if="store.error" class="mobile-error" role="alert">{{ store.error }} <button type="button" @click="store.refreshAfterMutation">重试</button></p>

    <nav v-if="activeTab !== 'review'" class="mobile-tabbar" aria-label="管理端移动导航">
      <Tabbar :model-value="activeTab" active-color="#1463f2" unactive-color="#94969e" :safe-area-inset-bottom="true" @update:model-value="goTab">
        <TabbarItem name="dashboard" tab-title="驾驶舱"><template #icon>◫</template></TabbarItem>
        <TabbarItem name="ranking" tab-title="排名"><template #icon>◇</template></TabbarItem>
        <TabbarItem name="learners" tab-title="学员"><template #icon>◎</template></TabbarItem>
        <TabbarItem name="plans" tab-title="任务"><template #icon>☷</template></TabbarItem>
      </Tabbar>
    </nav>

    <Popup v-model:visible="calendarOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div class="sheet"><div class="sheet-heading"><div><h2>统计观察范围</h2><p>仅改变观察窗口，不重置计划全周期进度</p></div><button type="button" @click="calendarOpen = false">×</button></div><CalendarCard v-model="selectedWeek" type="week" :first-day-of-week="1" /><button class="sheet-primary" type="button" @click="calendarOpen = false">使用此范围</button></div>
    </Popup>

    <Popup v-model:visible="planPickerOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div class="sheet"><div class="sheet-heading"><div><h2>选择训练计划</h2><p>计划完成度始终按计划全周期累计</p></div><button type="button" @click="planPickerOpen = false">×</button></div><button class="sheet-cell" :class="{ selected: selectedPlanId === 'all' }" type="button" @click="selectPlan('all')"><span><strong>全部进行中</strong><small>{{ store.activeTasks.length }} 个计划</small></span><b>✓</b></button><button v-for="task in store.activeTasks" :key="task.id" class="sheet-cell" :class="{ selected: selectedPlanId === task.id }" type="button" @click="selectPlan(task.id)"><span><strong>{{ task.title }}</strong><small>{{ taskItemLabel(task) }} · {{ task.assignment_count }}人</small></span><b>✓</b></button></div>
    </Popup>

    <Popup v-model:visible="learnerFilterOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div class="sheet"><div class="sheet-heading"><div><h2>筛选学员</h2><p>筛选条件会保留到返回列表</p></div><button type="button" @click="learnerFilterOpen = false">×</button></div><h3>状态</h3><div class="choice-grid"><button v-for="option in learnerStatusOptions" :key="option.value" type="button" :class="{ selected: learnerStatusFilter === option.value }" @click="learnerStatusFilter = option.value">{{ option.label }}</button></div><h3>训练计划</h3><div class="choice-grid"><button type="button" :class="{ selected: selectedPlanId === 'all' }" @click="selectedPlanId = 'all'">全部计划</button><button v-for="task in store.activeTasks" :key="task.id" type="button" :class="{ selected: selectedPlanId === task.id }" @click="selectedPlanId = task.id">{{ task.title }}</button></div><button class="sheet-primary" type="button" @click="learnerFilterOpen = false">完成</button></div>
    </Popup>

    <Popup v-model:visible="reviewFilterOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div class="sheet"><div class="sheet-heading"><div><h2>筛选复核任务</h2><p>支持按班组与 AI 异常优先排序</p></div><button type="button" @click="reviewFilterOpen = false">×</button></div><label class="switch-row"><span><strong>AI 异常优先</strong><small>优先显示异常或需重练项目</small></span><input v-model="reviewPriority" type="checkbox"></label><button class="sheet-primary" type="button" @click="reviewFilterOpen = false">完成</button></div>
    </Popup>

    <Popup v-model:visible="planDetailOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div v-if="selectedPlan" class="sheet plan-detail task-roster-sheet">
        <div class="sheet-heading"><div><h2>任务详情</h2><p>{{ selectedPlan.title }} · {{ dueLabel(selectedPlan) }}</p></div><button type="button" aria-label="关闭任务详情" @click="planDetailOpen = false">×</button></div>
        <template v-if="selectedPlanRosterLoading"><Skeleton width="100%" height="112px" animated /><div class="learner-progress-skeleton"><Skeleton width="100%" height="76px" animated /><Skeleton width="100%" height="76px" animated /></div></template>
        <section v-else-if="selectedPlanRosterError" class="learner-progress-feedback" role="alert"><strong>任务名单读取失败</strong><p>{{ selectedPlanRosterError }}</p><button type="button" @click="retrySelectedPlanRoster">重新加载</button></section>
        <template v-else-if="selectedPlanRoster">
          <div class="progress-state-grid" aria-label="任务完成状态"><span><strong>{{ selectedPlanRoster.not_started_count }}</strong><small>未开始</small></span><span><strong>{{ selectedPlanRoster.in_progress_count }}</strong><small>进行中</small></span><span><strong>{{ selectedPlanRoster.completed_count }}</strong><small>已完成</small></span></div>
          <div class="roster-summary-grid" aria-label="任务最终状态"><span><strong>{{ selectedPlanRoster.total_count }}</strong><small>总数</small></span><span class="success"><strong>{{ selectedPlanRoster.passed_count }}</strong><small>达标</small></span><span class="warning"><strong>{{ selectedPlanRoster.pending_review_count }}</strong><small>复核</small></span><span class="danger"><strong>{{ selectedPlanRoster.not_passed_count }}</strong><small>未达标</small></span></div>
          <section class="task-roster-list" aria-label="该任务人员完成情况">
            <article v-for="learner in selectedPlanRoster.learners" :key="learner.assignment_id">
              <i>{{ initial(learner.display_name) }}</i><div><strong>{{ learner.display_name }}</strong><small>{{ learner.external_ref || '未设置工号' }}{{ learner.class_name ? ` · ${learner.class_name}` : '' }}</small><Progress :percentage="learner.progress_percent" :show-text="false" :stroke-width="4" stroke-color="#1463f2" /></div><span><em :class="rosterProgressState(learner).tone">{{ rosterProgressState(learner).label }}</em><b>{{ learner.completed_items }}/{{ learner.total_items }} · {{ learner.progress_percent }}%</b></span>
            </article>
            <Empty v-if="!selectedPlanRoster.learners.length" description="该任务尚未分配人员" />
          </section>
          <p class="capability-note">名单仅包含该任务已分配人员；完成状态与最终达标状态分别统计。</p><button class="sheet-primary" type="button" @click="lightEditOpen = true">轻编辑</button>
        </template>
      </div>
    </Popup>

    <Popup v-model:visible="lightEditOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup nested-popup">
      <div v-if="selectedPlan" class="sheet"><div class="sheet-heading"><div><h2>轻编辑计划</h2><p>{{ selectedPlan.title }}</p></div><button type="button" @click="lightEditOpen = false">×</button></div><label class="readonly-field"><span>截止时间</span><strong>{{ dueLabel(selectedPlan) }}</strong><small>当前服务端暂未开放安全更新接口</small></label><label class="readonly-field"><span>参与人员</span><strong>已分配 {{ selectedPlan.assignment_count }} 人</strong><small>增删参与人员需在 PC 后台完成，避免覆盖历史提交</small></label><p v-if="taskActionError" class="inline-error">{{ taskActionError }}</p><button class="sheet-primary" type="button" :disabled="taskSaving" @click="togglePlanStatus">{{ selectedPlan.status === 'closed' ? '恢复计划' : '暂停计划' }}</button></div>
    </Popup>

    <Popup v-model:visible="reviewDetailOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup">
      <div v-if="selectedReview" class="sheet review-detail"><div class="sheet-heading"><div><h2>复核详情</h2><p>{{ selectedReview.learnerName }} · {{ selectedReview.taskTitle }}</p></div><button type="button" @click="closeReview">×</button></div><Skeleton v-if="reviewDetailLoading" width="100%" height="220px" animated /><template v-else><div class="ai-score"><span>AI 综合评分</span><strong>{{ reviewDetail?.overall_score ?? '—' }}</strong><b>{{ reviewFocus }}</b></div><section class="audio-state"><div><strong>学员录音</strong><small>{{ audioStateLabel }}</small></div><button v-if="!audioUrl && !audioLoading && audioState !== 'error'" type="button" @click="loadAudio">▶</button><Skeleton v-else-if="audioLoading" width="100%" height="48px" animated /><Audio v-else-if="audioUrl" :url="audioUrl" type="controls" @play="audioState = 'playing'" @ended="audioState = 'ready'" /><Empty v-else-if="audioState === 'error'" image="error" description="录音加载失败，可稍后重试" /><button v-if="audioState === 'error'" type="button" aria-label="重试加载录音" @click="loadAudio">↻</button></section><div class="review-form"><label><span>人工总分</span><input v-model.number="manualScore" type="number" min="0" max="100" inputmode="decimal"></label><label><span>复核备注</span><textarea v-model="reviewNote" rows="2" placeholder="填写复核依据"></textarea></label></div><div class="sheet-actions"><button type="button" @click="askReviewAction('return')">退回重练</button><button class="primary" type="button" @click="askReviewAction('pass')">确认通过</button></div><p class="capability-note">确认后同步更新学习质量维度与最终状态；AI 与人工复核记录均保留。</p><p v-if="reviewActionError" class="inline-error">{{ reviewActionError }}</p></template></div>
    </Popup>

    <Dialog v-model:visible="confirmOpen" :title="confirmAction === 'pass' ? '确认通过复核？' : '确认退回重练？'" :content="confirmAction === 'pass' ? '通过后将更新学员质量维度与最终状态；本次人工评分会保留。' : '该任务将重新进入学员待完成列表，并保留本次 AI 与人工复核记录。'" cancel-text="取消" :ok-text="confirmAction === 'pass' ? '确认通过' : '确认退回'" text-align="left" @ok="confirmReview" />

    <Popup :visible="Boolean(selectedLearner)" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup" @update:visible="value => { if (!value) closeLearner() }">
      <div v-if="selectedLearner" class="sheet learner-progress-sheet">
        <div class="sheet-heading"><div><h2>学员进度</h2><p>{{ selectedLearner.display_name }} · {{ selectedLearner.external_ref || '未设置工号' }}</p></div><button type="button" aria-label="关闭学员进度" @click="closeLearner">×</button></div>
        <template v-if="selectedLearnerLoading">
          <Skeleton width="100%" height="112px" animated />
          <div class="learner-progress-skeleton"><Skeleton width="100%" height="126px" animated /><Skeleton width="100%" height="126px" animated /></div>
        </template>
        <section v-else-if="selectedLearnerError" class="learner-progress-feedback" role="alert">
          <strong>进度读取失败</strong><p>{{ selectedLearnerError }}</p><button type="button" @click="retryLearnerTasks">重新加载</button>
        </section>
        <template v-else>
          <section class="learner-progress-summary" aria-label="学员完成进度汇总">
            <div><span>{{ selectedPlanId === 'all' ? '全部计划完成进度' : '当前计划完成进度' }}</span><strong>{{ selectedLearnerSummary.rate }}%</strong><small>{{ selectedLearnerSummary.completedItems }} / {{ selectedLearnerSummary.totalItems }} 个任务项已完成</small></div>
            <Progress :percentage="selectedLearnerSummary.rate" :show-text="false" :stroke-width="6" stroke-color="#1463f2" />
            <div class="learner-progress-kpis"><span><b>{{ selectedLearnerSummary.plans }}</b><small>已分配计划</small></span><span><b>{{ selectedLearnerSummary.completedPlans }}</b><small>已完成计划</small></span><span><b>{{ selectedLearnerSummary.pending }}</b><small>待复核</small></span></div>
          </section>
          <section v-if="selectedLearnerTasks.length" class="learner-progress-list" aria-label="训练计划完成明细">
            <article v-for="task in selectedLearnerTasks" :key="task.assignment_id" class="learner-progress-card">
              <header><div><span>{{ learnerTaskType(task) }}</span><strong>{{ task.title }}</strong></div><em :class="learnerTaskState(task).tone">{{ learnerTaskState(task).label }}</em></header>
              <div class="learner-progress-line"><Progress :percentage="task.progress_percent" :show-text="false" :stroke-width="5" stroke-color="#1463f2" /><b>{{ task.progress_percent }}%</b></div>
              <dl><div><dt>完成内容</dt><dd>{{ task.completed_items }} / {{ task.total_items }} 项</dd></div><div><dt>练习次数</dt><dd>{{ task.attempt_count }} 次</dd></div><div><dt>截止时间</dt><dd>{{ learnerTaskDue(task) }}</dd></div></dl>
              <p v-if="task.locked && task.unlock_reason">{{ task.unlock_reason }}</p>
            </article>
          </section>
          <Empty v-else description="当前筛选范围没有分配给该学员的训练计划" />
          <section class="learner-broadcast-section" aria-label="广播词完成明细">
            <header><div><h3>广播词完成明细</h3><p>点击已练习的广播词，查看录音与测评详情</p></div><b>{{ selectedLearnerBroadcasts.length }} 项</b></header>
            <div v-if="selectedLearnerBroadcastLoading" class="learner-progress-skeleton"><Skeleton width="100%" height="68px" animated /><Skeleton width="100%" height="68px" animated /></div>
            <section v-else-if="selectedLearnerBroadcastError" class="learner-progress-feedback compact" role="alert"><strong>广播词明细读取失败</strong><p>{{ selectedLearnerBroadcastError }}</p><button type="button" @click="retryLearnerBroadcasts">重新加载</button></section>
            <div v-else class="learner-broadcast-list">
              <button v-for="item in selectedLearnerBroadcasts" :key="`${item.assignment_id}:${item.content_item_id}`" type="button" :disabled="!item.latest_attempt_id" @click="openLearnerAttempt(item)">
                <span><strong>{{ item.content_title }}</strong><small>{{ item.task_title }} · {{ item.chapter_title }} · 已练 {{ item.attempt_count }} 次</small></span><em :class="broadcastState(item).tone">{{ broadcastState(item).label }}</em><b>{{ item.latest_attempt_id ? '›' : '—' }}</b>
              </button>
              <Empty v-if="!selectedLearnerBroadcasts.length" description="当前筛选范围没有广播词任务" />
            </div>
          </section>
          <p class="learner-progress-note">完成进度与最终达标分开统计；待复核不会提前计入已达标。</p>
        </template>
      </div>
    </Popup>

    <Popup v-model:visible="learnerAttemptOpen" position="bottom" round :safe-area-inset-bottom="true" class="mobile-popup nested-popup">
      <div class="sheet learner-attempt-sheet">
        <div class="sheet-heading"><div><h2>音频与测评详情</h2><p>{{ selectedBroadcast?.content_title || '广播词练习' }}</p></div><button type="button" aria-label="关闭音频与测评详情" @click="closeLearnerAttempt">×</button></div>
        <Skeleton v-if="learnerAttemptLoading" width="100%" height="280px" animated />
        <section v-else-if="learnerAttemptError" class="learner-progress-feedback" role="alert"><strong>详情读取失败</strong><p>{{ learnerAttemptError }}</p><button type="button" @click="retryLearnerAttempt">重新加载</button></section>
        <template v-else-if="learnerAttemptDetail">
          <div class="ai-score"><span>AI 综合评分</span><strong>{{ learnerAttemptDetail.overall_score ?? selectedBroadcast?.latest_score ?? '—' }}</strong><b>{{ aiStatusLabel(learnerAttemptDetail.ai_status) }}</b></div>
          <section class="audio-state"><div><strong>学员录音</strong><small>{{ learnerAudioStateLabel }}</small></div><button v-if="!learnerAudioUrl && !learnerAudioLoading && learnerAudioState !== 'error'" type="button" @click="loadLearnerAudio">▶</button><Skeleton v-else-if="learnerAudioLoading" width="100%" height="48px" animated /><Audio v-else-if="learnerAudioUrl" :url="learnerAudioUrl" type="controls" @play="learnerAudioState = 'playing'" @ended="learnerAudioState = 'ready'" /><Empty v-else-if="learnerAudioState === 'error'" image="error" description="录音加载失败，可重新尝试" /><button v-if="learnerAudioState === 'error'" type="button" aria-label="重试加载学员录音" @click="loadLearnerAudio">↻</button></section>
          <div class="learner-score-grid"><span v-for="score in learnerScoreItems" :key="score.label"><small>{{ score.label }}</small><strong>{{ score.value }}</strong></span></div>
          <section class="transcript-card"><h3>广播词原文</h3><p>{{ learnerAttemptDetail.reference_text || '暂无原文' }}</p><h3>识别文本</h3><p>{{ learnerAttemptDetail.recognized_text || '暂无识别文本' }}</p></section>
          <section class="issue-card"><h3>测评问题 <b>{{ learnerAttemptDetail.ai_issues.length }}</b></h3><ul v-if="learnerAttemptDetail.ai_issues.length"><li v-for="(issue, index) in learnerAttemptDetail.ai_issues" :key="index"><strong>{{ issue.dimension || issue.type || '测评提示' }}</strong><span>{{ issue.message || issue.training_advice || `${issue.expected || ''}${issue.actual ? ` → ${issue.actual}` : ''}` || '请结合原文与录音复核' }}</span></li></ul><Empty v-else description="本次测评未返回问题项" /></section>
          <section v-if="learnerAttemptDetail.review" class="teacher-review-card"><h3>人工复核</h3><strong>{{ learnerAttemptDetail.review.final_score ?? '未评分' }} 分 · {{ learnerAttemptDetail.review.status === 'published' ? '已发布' : '草稿' }}</strong><p>{{ learnerAttemptDetail.review.correction_advice || learnerAttemptDetail.review.summary || '暂无复核建议' }}</p></section>
          <p class="capability-note">该页面为只读详情；保留原始录音、AI 测评证据与人工复核结果。</p>
        </template>
      </div>
    </Popup>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Audio,
  CalendarCard,
  CircleProgress,
  Dialog,
  Empty,
  Popup,
  Progress,
  Searchbar,
  Skeleton,
  Tabbar,
  TabbarItem,
  TabPane,
  Tabs,
} from '@nutui/nutui'
import '@nutui/nutui/dist/style.css'
import { cabinlingoApi, type AdminLearnerBroadcastItem, type InstructorReviewDetail, type InstructorReviewPayload, type LearnerTask, type TaskListItem, type TaskRosterLearner, type UserSummary } from '@/api'
import { useAdminMobileStore, type MobileReviewItem } from '@/stores/adminMobile'

type MobileTab = 'dashboard' | 'ranking' | 'learners' | 'plans' | 'review'
type LearnerFilter = 'all' | 'passed' | 'pending' | 'not-passed'

const MobileHeader = defineComponent({
  props: { title: { type: String, required: true }, subtitle: { type: String, required: true } },
  setup: (props) => () => h('div', { class: 'mobile-heading' }, [h('h1', props.title), h('p', props.subtitle)]),
})
const FilterTrigger = defineComponent({
  props: { label: { type: String, required: true } },
  emits: ['click'],
  setup: (props, { emit }) => () => h('button', { class: 'filter-trigger', type: 'button', onClick: () => emit('click') }, [h('span', props.label), h('b', '⌄')]),
})
const RankingEmpty = defineComponent({
  setup: () => () => h('div', { class: 'ranking-empty' }, [h(Empty, { description: '试算排名等待个人指标与后台权重接口' }), h('p', '不会用演示权重或虚构分数生成正式榜单。')]),
})

const route = useRoute()
const router = useRouter()
const store = useAdminMobileStore()
const calendarOpen = ref(false)
const planPickerOpen = ref(false)
const learnerFilterOpen = ref(false)
const reviewFilterOpen = ref(false)
const planDetailOpen = ref(false)
const lightEditOpen = ref(false)
const reviewDetailOpen = ref(false)
const confirmOpen = ref(false)
const selectedWeek = ref<Date[]>(currentWeek())
const selectedPlanId = ref('all')
const selectedPlan = ref<TaskListItem | null>(null)
const selectedReview = ref<MobileReviewItem | null>(null)
const selectedLearner = ref<UserSummary | null>(null)
const selectedBroadcast = ref<AdminLearnerBroadcastItem | null>(null)
const learnerAttemptOpen = ref(false)
const learnerAttemptDetail = ref<InstructorReviewDetail | null>(null)
const learnerAttemptLoading = ref(false)
const learnerAttemptError = ref('')
const learnerAudioUrl = ref('')
const learnerAudioLoading = ref(false)
const learnerAudioState = ref<'idle' | 'ready' | 'playing' | 'error'>('idle')
const learnerSearch = ref('')
const reviewSearch = ref('')
const learnerStatusFilter = ref<LearnerFilter>('all')
const deferredLearnerFilter = ref<LearnerFilter | null>(null)
const groupFilter = ref('全部组')
const reviewPriority = ref(true)
const rankingTab = ref(0)
const reviewDetail = ref<InstructorReviewDetail | null>(null)
const reviewDetailLoading = ref(false)
const reviewNote = ref('')
const manualScore = ref<number | null>(null)
const audioUrl = ref('')
const audioLoading = ref(false)
const audioState = ref<'idle' | 'ready' | 'playing' | 'error'>('idle')
const confirmAction = ref<'pass' | 'return'>('pass')
const reviewActionError = ref('')
const taskActionError = ref('')
const taskSaving = ref(false)

const activeTab = computed<MobileTab>(() => {
  const requested = String(route.query.mobile || '')
  if (['ranking', 'learners', 'plans', 'review'].includes(requested)) return requested as MobileTab
  const section = String(route.params.section || 'dashboard')
  if (section === 'users') return 'learners'
  if (section === 'tasks') return 'plans'
  return 'dashboard'
})
const weekLabel = computed(() => `统计观察范围 · ${formatWeek(selectedWeek.value)}`)
const selectedPlanLabel = computed(() => selectedPlanId.value === 'all' ? '任务计划 · 全部进行中' : `任务计划 · ${store.tasks.find((task) => task.id === selectedPlanId.value)?.title || '全部进行中'}`)
const visiblePlans = computed(() => selectedPlanId.value === 'all' ? store.activeTasks.slice(0, 3) : store.activeTasks.filter((task) => task.id === selectedPlanId.value))
const mobilePlans = computed(() => store.tasks.filter((task) => ['published', 'open', 'closed'].includes(task.status)))
const currentTask = computed(() => store.tasks.find((item) => item.id === selectedPlanId.value) || null)
const currentTaskRosterKey = computed(() => currentTask.value ? `${currentTask.value.task_type}:${currentTask.value.id}` : '')
const currentTaskRoster = computed(() => currentTaskRosterKey.value ? store.taskRosters[currentTaskRosterKey.value] || null : null)
const currentTaskRosterLoading = computed(() => Boolean(currentTaskRosterKey.value && store.taskRosterLoading[currentTaskRosterKey.value]))
const currentTaskRosterError = computed(() => currentTaskRosterKey.value ? store.taskRosterError[currentTaskRosterKey.value] || '' : '')
const selectedPlanRosterKey = computed(() => selectedPlan.value ? `${selectedPlan.value.task_type}:${selectedPlan.value.id}` : '')
const selectedPlanRoster = computed(() => selectedPlanRosterKey.value ? store.taskRosters[selectedPlanRosterKey.value] || null : null)
const selectedPlanRosterLoading = computed(() => Boolean(selectedPlanRosterKey.value && store.taskRosterLoading[selectedPlanRosterKey.value]))
const selectedPlanRosterError = computed(() => selectedPlanRosterKey.value ? store.taskRosterError[selectedPlanRosterKey.value] || '' : '')
const dashboardLoading = computed(() => (store.loading && !store.loaded) || currentTaskRosterLoading.value)
const currentStats = computed(() => {
  const task = currentTask.value
  const roster = currentTaskRoster.value
  if (task && roster) {
    const submitted = roster.completed_count
    return {
      total: roster.total_count,
      submitted,
      pending: roster.pending_review_count,
      passed: roster.passed_count,
      notPassed: roster.not_passed_count,
      finalRate: roster.total_count ? Math.round(roster.passed_count / roster.total_count * 100) : 0,
      submissionRate: roster.total_count ? Math.round(submitted / roster.total_count * 100) : 0,
    }
  }
  const activeRosters = store.activeTasks
    .map((item) => store.taskRosters[`${item.task_type}:${item.id}`])
    .filter((item): item is NonNullable<typeof item> => Boolean(item))
  if (!task && activeRosters.length === store.activeTasks.length && activeRosters.length) {
    const total = activeRosters.reduce((sum, item) => sum + item.total_count, 0)
    const submitted = activeRosters.reduce((sum, item) => sum + item.completed_count, 0)
    const pending = activeRosters.reduce((sum, item) => sum + item.pending_review_count, 0)
    const passed = activeRosters.reduce((sum, item) => sum + item.passed_count, 0)
    const notPassed = activeRosters.reduce((sum, item) => sum + item.not_passed_count, 0)
    return { total, submitted, pending, passed, notPassed, finalRate: total ? Math.round(passed / total * 100) : 0, submissionRate: total ? Math.round(submitted / total * 100) : 0 }
  }
  const total = task?.assignment_count ?? store.totalAssignments
  const submitted = Math.min(task?.completed_count ?? store.submittedCount, total)
  const pending = new Set(store.reviews.filter((item) => !task || item.taskId === task.id).map((item) => item.assignmentId)).size
  const passed = Math.max(submitted - pending, 0)
  const notPassed = Math.max(total - submitted, 0)
  return { total, submitted, pending, passed, notPassed, finalRate: total ? Math.round(passed / total * 100) : 0, submissionRate: total ? Math.round(submitted / total * 100) : 0 }
})
const pendingLearnerIds = computed(() => new Set(store.reviews.map((item) => item.learnerId)))
const currentRosterByLearner = computed(() => new Map((currentTaskRoster.value?.learners || []).map((item) => [item.learner_id, item])))
const filteredLearners = computed(() => {
  const roster = currentTaskRoster.value
  const users: UserSummary[] = roster ? roster.learners.map((item) => ({ id: item.learner_id, external_ref: item.external_ref, display_name: item.display_name, email: null, is_active: true, roles: ['learner'], class_id: null })) : store.learnerUsers
  return users.filter((user) => {
  const query = learnerSearch.value.trim().toLowerCase()
  if (query && !`${user.display_name} ${user.external_ref || ''}`.toLowerCase().includes(query)) return false
  const rosterItem = currentRosterByLearner.value.get(user.id)
  if (rosterItem) {
    if (learnerStatusFilter.value === 'passed') return rosterItem.final_status === 'passed'
    if (learnerStatusFilter.value === 'pending') return rosterItem.final_status === 'pending_review'
    if (learnerStatusFilter.value === 'not-passed') return rosterItem.final_status === 'not_passed'
    return true
  }
  if (learnerStatusFilter.value === 'pending') return pendingLearnerIds.value.has(user.id)
  if (learnerStatusFilter.value !== 'all') return false
  return true
  })
})
const filteredReviews = computed(() => {
  const query = reviewSearch.value.trim().toLowerCase()
  const items = store.reviews.filter((item) => !query || `${item.learnerName} ${item.taskTitle}`.toLowerCase().includes(query))
  return reviewPriority.value ? [...items].sort((a, b) => Number(b.priority !== 'normal') - Number(a.priority !== 'normal')) : items
})
const statusFilterLabel = computed(() => learnerStatusOptions.find((item) => item.value === learnerStatusFilter.value)?.label || '全部状态')
const planFilterLabel = computed(() => selectedPlanId.value === 'all' ? '全部计划' : store.tasks.find((task) => task.id === selectedPlanId.value)?.title || '全部计划')
const reviewFocus = computed(() => reviewDetail.value?.ai_issues.slice(0, 2).map((item) => item.dimension || item.type).filter(Boolean).join(' / ') || '重点：等待 AI 明细')
const audioStateLabel = computed(() => audioState.value === 'playing' ? '播放中' : audioState.value === 'error' ? '加载失败' : audioState.value === 'ready' ? '已就绪' : '点击加载录音')
const selectedLearnerTasks = computed(() => {
  if (!selectedLearner.value) return []
  const items = store.learnerTasksByUser[selectedLearner.value.id] || []
  return selectedPlanId.value === 'all' ? items : items.filter((item) => item.task_id === selectedPlanId.value)
})
const selectedLearnerLoading = computed(() => Boolean(selectedLearner.value && store.learnerTasksLoading[selectedLearner.value.id]))
const selectedLearnerError = computed(() => selectedLearner.value ? store.learnerTasksError[selectedLearner.value.id] || '' : '')
const selectedLearnerBroadcasts = computed(() => {
  if (!selectedLearner.value) return []
  const items = store.learnerBroadcastsByUser[selectedLearner.value.id] || []
  return selectedPlanId.value === 'all' ? items : items.filter((item) => item.task_id === selectedPlanId.value)
})
const selectedLearnerBroadcastLoading = computed(() => Boolean(selectedLearner.value && store.learnerBroadcastsLoading[selectedLearner.value.id]))
const selectedLearnerBroadcastError = computed(() => selectedLearner.value ? store.learnerBroadcastsError[selectedLearner.value.id] || '' : '')
const learnerAudioStateLabel = computed(() => learnerAudioState.value === 'playing' ? '播放中' : learnerAudioState.value === 'error' ? '加载失败' : learnerAudioState.value === 'ready' ? '已就绪' : '点击加载录音')
const learnerScoreItems = computed(() => {
  const scores = learnerAttemptDetail.value?.ai_scores || {}
  return [
    { label: '完整度', value: scores.completeness ?? '—' },
    { label: '发音', value: scores.pronunciation ?? '—' },
    { label: '流利度', value: scores.fluency ?? '—' },
    { label: '表达', value: scores.expression ?? '—' },
  ]
})
const selectedLearnerSummary = computed(() => {
  const tasks = selectedLearnerTasks.value
  const totalItems = tasks.reduce((sum, task) => sum + task.total_items, 0)
  const completedItems = tasks.reduce((sum, task) => sum + task.completed_items, 0)
  const pendingAssignmentIds = new Set(currentTaskRoster.value?.learners.filter((item) => item.pending_review).map((item) => item.assignment_id) || store.reviews.map((item) => item.assignmentId))
  return {
    plans: tasks.length,
    completedPlans: tasks.filter((task) => task.progress_percent >= 100).length,
    completedItems,
    totalItems,
    pending: tasks.filter((task) => pendingAssignmentIds.has(task.assignment_id)).length,
    rate: totalItems ? Math.round(completedItems / totalItems * 100) : 0,
  }
})
const learnerStatusOptions: Array<{ value: LearnerFilter; label: string }> = [{ value: 'all', label: '全部状态' }, { value: 'passed', label: '已达标' }, { value: 'pending', label: '待复核' }, { value: 'not-passed', label: '未达标' }]

onMounted(() => void store.refresh())
onBeforeUnmount(() => { revokeAudio(); revokeLearnerAudio() })

function currentWeek() {
  const now = new Date()
  const day = now.getDay() || 7
  const monday = new Date(now)
  monday.setHours(0, 0, 0, 0)
  monday.setDate(now.getDate() - day + 1)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return [monday, sunday]
}
function formatWeek(value: Date[]) {
  if (value.length < 2) return '本周'
  const date = (item: Date) => `${item.getMonth() + 1}/${item.getDate()}`
  return `本周 · ${date(value[0])}—${date(value[1])}`
}
function goTab(value: string | number) {
  const tab = String(value) as MobileTab
  const target = tab === 'learners' ? '/admin/users' : tab === 'plans' ? '/admin/tasks' : '/admin/dashboard'
  const query = tab === 'dashboard' ? {} : { mobile: tab }
  void router.replace({ path: target, query })
}
function openReviewQueue() { void router.replace({ path: '/admin/dashboard', query: { mobile: 'review' } }) }
function openLearners(status: LearnerFilter) {
  learnerStatusFilter.value = status
  if (selectedPlanId.value === 'all') { deferredLearnerFilter.value = status; planPickerOpen.value = true; return }
  if (currentTask.value) void store.loadTaskRoster(currentTask.value)
  goTab('learners')
}
function selectPlan(id: string) {
  selectedPlanId.value = id
  planPickerOpen.value = false
  const task = store.tasks.find((item) => item.id === id)
  if (task) void store.loadTaskRoster(task)
  if (deferredLearnerFilter.value && task) { learnerStatusFilter.value = deferredLearnerFilter.value; deferredLearnerFilter.value = null; goTab('learners') }
  else if (id === 'all') deferredLearnerFilter.value = null
}
function taskRate(task: TaskListItem) { return task.assignment_count ? Math.round(task.completed_count / task.assignment_count * 100) : 0 }
function taskItemLabel(task: TaskListItem) { return task.broadcast_script_count > 0 ? `${task.broadcast_script_count}项必做` : '任务项数按计划配置' }
function dueLabel(task: TaskListItem) { return task.due_at ? `${new Date(task.due_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${new Date(task.due_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })} 截止` : '未设置截止时间' }
function initial(name: string) { return name.trim().slice(0, 1) || '员' }
function timeLabel(value: string | null) { return value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }) : '时间待同步' }
function aiStatusLabel(value: string) { return value && value !== 'completed' ? `AI ${value}` : 'AI 已完成' }
function learnerState(user: UserSummary) {
  const rosterItem = currentRosterByLearner.value.get(user.id)
  if (rosterItem?.final_status === 'passed') return { label: '已达标', tone: 'success' }
  if (rosterItem?.final_status === 'pending_review') return { label: '待复核', tone: 'warning' }
  if (rosterItem?.final_status === 'not_passed') return { label: '未达标', tone: 'danger' }
  if (pendingLearnerIds.value.has(user.id)) return { label: '待复核', tone: 'warning' }
  const tasks = store.learnerTasksByUser[user.id]
  if (!tasks) return { label: '查看进度', tone: 'neutral' }
  if (!tasks.length) return { label: '未分配', tone: 'neutral' }
  if (tasks.every((task) => task.progress_percent >= 100)) return { label: '已完成', tone: 'success' }
  if (tasks.some((task) => task.progress_percent > 0)) return { label: '进行中', tone: 'active' }
  return { label: '未开始', tone: 'neutral' }
}
function learnerSubline(user: UserSummary) {
  const rosterItem = currentRosterByLearner.value.get(user.id)
  const progress = rosterItem ? ` · ${rosterProgressState(rosterItem).label} ${rosterItem.progress_percent}%` : ''
  return `${user.external_ref || '未设置工号'}${progress}`
}
function openLearner(user: UserSummary) { selectedLearner.value = user; void Promise.all([store.loadLearnerTasks(user.id), store.loadLearnerBroadcasts(user.id)]) }
function closeLearner() { closeLearnerAttempt(); selectedLearner.value = null }
function retryLearnerTasks() { if (selectedLearner.value) void Promise.all([store.loadLearnerTasks(selectedLearner.value.id, true), store.loadLearnerBroadcasts(selectedLearner.value.id, true)]) }
function retryLearnerBroadcasts() { if (selectedLearner.value) void store.loadLearnerBroadcasts(selectedLearner.value.id, true) }
function broadcastState(item: AdminLearnerBroadcastItem) {
  if (item.review_status === 'pending_review' || item.review_status === 'draft') return { label: '待复核', tone: 'warning' }
  if (item.review_status === 'published') return { label: '已复核', tone: 'success' }
  if (item.progress_status === 'completed') return { label: '已完成', tone: 'success' }
  if (item.progress_status === 'in_progress') return { label: '进行中', tone: 'active' }
  return { label: '未开始', tone: 'neutral' }
}
async function openLearnerAttempt(item: AdminLearnerBroadcastItem) {
  if (!selectedLearner.value || !item.latest_attempt_id) return
  selectedBroadcast.value = item
  learnerAttemptOpen.value = true
  learnerAttemptDetail.value = null
  learnerAttemptError.value = ''
  revokeLearnerAudio()
  learnerAttemptLoading.value = true
  try { learnerAttemptDetail.value = await cabinlingoApi.adminLearnerAttemptDetail(selectedLearner.value.id, item.latest_attempt_id) }
  catch { learnerAttemptError.value = '音频与测评详情暂时无法读取，请检查权限或网络后重试。' }
  finally { learnerAttemptLoading.value = false }
}
function retryLearnerAttempt() { if (selectedBroadcast.value) void openLearnerAttempt(selectedBroadcast.value) }
function closeLearnerAttempt() { learnerAttemptOpen.value = false; learnerAttemptDetail.value = null; learnerAttemptError.value = ''; selectedBroadcast.value = null; revokeLearnerAudio() }
async function loadLearnerAudio() {
  const source = learnerAttemptDetail.value?.recording_url || learnerAttemptDetail.value?.recordings[0]?.audio_url
  if (!source || learnerAudioLoading.value) { learnerAudioState.value = 'error'; return }
  learnerAudioLoading.value = true
  learnerAudioState.value = 'idle'
  try { learnerAudioUrl.value = URL.createObjectURL(await cabinlingoApi.protectedAudio(source)); learnerAudioState.value = 'ready' }
  catch { learnerAudioState.value = 'error' }
  finally { learnerAudioLoading.value = false }
}
function revokeLearnerAudio() { if (learnerAudioUrl.value) URL.revokeObjectURL(learnerAudioUrl.value); learnerAudioUrl.value = ''; learnerAudioState.value = 'idle' }
function learnerTaskType(task: LearnerTask) { return task.task_type === 'exam' ? '考试' : '训练' }
function learnerTaskState(task: LearnerTask) {
  if (store.reviews.some((item) => item.assignmentId === task.assignment_id)) return { label: '待复核', tone: 'warning' }
  if (task.locked) return { label: '未解锁', tone: 'neutral' }
  if (task.progress_percent >= 100) return { label: '已完成', tone: 'success' }
  if (task.status === 'closed') return { label: '已暂停', tone: 'neutral' }
  if (task.progress_percent > 0) return { label: '进行中', tone: 'active' }
  return { label: '未开始', tone: 'neutral' }
}
function learnerTaskDue(task: LearnerTask) { return task.due_at ? new Date(task.due_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '未设置' }
function rosterProgressState(learner: TaskRosterLearner) {
  if (learner.progress_status === 'completed') return { label: '已完成', tone: 'success' }
  if (learner.progress_status === 'in_progress') return { label: '进行中', tone: 'active' }
  return { label: '未开始', tone: 'neutral' }
}
function retryCurrentTaskRoster() { if (currentTask.value) void store.loadTaskRoster(currentTask.value, true) }
function retrySelectedPlanRoster() { if (selectedPlan.value) void store.loadTaskRoster(selectedPlan.value, true) }
function openPlanDetail(task: TaskListItem) { selectedPlan.value = task; selectedPlanId.value = task.id; taskActionError.value = ''; planDetailOpen.value = true; void store.loadTaskRoster(task) }

async function togglePlanStatus() {
  if (!selectedPlan.value || taskSaving.value) return
  taskSaving.value = true
  taskActionError.value = ''
  try {
    const action = selectedPlan.value.status === 'closed' ? 'publish' : 'close'
    await store.changeTaskStatus(selectedPlan.value, action)
    selectedPlan.value = store.tasks.find((task) => task.id === selectedPlan.value?.id) || null
    lightEditOpen.value = false
  } catch {
    taskActionError.value = '计划状态更新失败，请检查权限或网络后重试。'
  } finally {
    taskSaving.value = false
  }
}

async function openReview(item: MobileReviewItem) {
  selectedReview.value = item
  reviewDetail.value = null
  reviewNote.value = ''
  manualScore.value = null
  reviewActionError.value = ''
  reviewDetailOpen.value = true
  revokeAudio()
  if (!item.reviewType || !item.targetId) return
  reviewDetailLoading.value = true
  try {
    reviewDetail.value = await cabinlingoApi.instructorReview(item.reviewType, item.targetId)
    reviewNote.value = reviewDetail.value.review?.correction_advice || ''
    manualScore.value = reviewDetail.value.review?.final_score ?? reviewDetail.value.overall_score
  } catch {
    reviewActionError.value = '复核详情暂时无法读取，列表筛选条件已保留。'
  } finally {
    reviewDetailLoading.value = false
  }
}
function closeReview() { reviewDetailOpen.value = false; revokeAudio(); selectedReview.value = null }
async function loadAudio() {
  const source = reviewDetail.value?.recording_url || reviewDetail.value?.recordings[0]?.audio_url
  if (!source || audioLoading.value) { audioState.value = 'error'; return }
  audioLoading.value = true
  audioState.value = 'idle'
  try { audioUrl.value = URL.createObjectURL(await cabinlingoApi.protectedAudio(source)); audioState.value = 'ready' }
  catch { audioState.value = 'error' }
  finally { audioLoading.value = false }
}
function revokeAudio() { if (audioUrl.value) URL.revokeObjectURL(audioUrl.value); audioUrl.value = ''; audioState.value = 'idle' }
function askReviewAction(action: 'pass' | 'return') { confirmAction.value = action; reviewActionError.value = ''; confirmOpen.value = true }
function reviewPayload(retraining: boolean): InstructorReviewPayload {
  const scores = reviewDetail.value?.ai_scores || {}
  return { completeness_score: scores.completeness ?? null, pronunciation_score: scores.pronunciation ?? null, fluency_score: scores.fluency ?? null, expression_score: scores.expression ?? null, final_score: manualScore.value, evidence: { source: 'mobile_admin', ai_status: reviewDetail.value?.ai_status || selectedReview.value?.aiStatus }, summary: retraining ? '管理员退回重练' : '管理员确认通过', correction_advice: reviewNote.value.trim(), required_retraining: retraining, remediation_due_at: null }
}
async function confirmReview() {
  if (!selectedReview.value) return
  const retraining = confirmAction.value === 'return'
  try {
    if (selectedReview.value.reviewType && selectedReview.value.targetId) {
      await cabinlingoApi.publishInstructorReview(selectedReview.value.reviewType, selectedReview.value.targetId, reviewPayload(retraining))
    } else if (!retraining) {
      await cabinlingoApi.saveReview(selectedReview.value.assignmentId, { manual_score: manualScore.value ?? 0, comments: reviewNote.value.trim(), publish: true })
    } else {
      reviewActionError.value = '该历史复核记录缺少退回重练接口，请在 PC 教员工作台处理。'
      return
    }
    closeReview()
    await store.refreshAfterMutation()
  } catch {
    reviewActionError.value = '复核提交失败，请检查权限或网络后重试。'
  }
}
</script>

<style scoped>
.admin-mobile{--m-blue:#1463f2;--m-ink:#12141a;--m-copy:#293852;--m-muted:#6b788c;--m-faint:#94969e;--m-line:#e3eaf3;min-height:100dvh;color:var(--m-ink);background:#f6f9fc;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}.mobile-page{width:min(100%,430px);min-height:100dvh;margin:0 auto;padding:20px 20px calc(104px + env(safe-area-inset-bottom))}:deep(.mobile-heading h1){margin:0;font-size:24px;line-height:1.22;letter-spacing:-.02em}:deep(.mobile-heading p){margin:8px 0 13px;color:var(--m-faint);font-size:11px;line-height:1.55}.filter-trigger{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:44px;margin-bottom:4px;padding:0 12px;border:1px solid var(--m-line);border-radius:14px;color:var(--m-copy);background:#fff;text-align:left;font-size:12px;font-weight:600}.filter-trigger b{color:var(--m-blue);font-size:14px}.mobile-skeleton{display:grid;gap:14px;margin-top:10px}.hero-card{position:relative;width:100%;min-height:102px;margin:10px 0 16px;padding:17px 112px 14px 18px;border-radius:22px;color:#fff;background:linear-gradient(135deg,#206df5,var(--m-blue));text-align:left}.hero-card>span,.hero-card>strong,.hero-card>small{display:block}.hero-card>span{font-size:11px}.hero-card>strong{margin-top:6px;font-size:34px;line-height:1}.hero-card>small{margin-top:8px;color:#e5f0ff;font-size:10px;line-height:1.4;white-space:nowrap}.hero-ring{position:absolute!important;right:17px;top:17px}.hero-ring b{color:#fff;font-size:14px}.state-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:17px}.state-card{position:relative;min-height:70px;padding:11px;border:1px solid var(--m-line);border-radius:16px;background:#fff;text-align:left}.state-card span,.state-card strong{display:block}.state-card span{color:var(--m-muted);font-size:10px}.state-card strong{margin-top:8px;font-size:24px}.state-card small{position:absolute;right:10px;bottom:7px;color:var(--m-faint);font-size:9px}.success,.state-card.success strong{color:#21ad59}.warning,.state-card.warning strong{color:#f58c1f}.danger,.state-card.danger strong{color:#eb3338}.mobile-card{border:1px solid var(--m-line);border-radius:18px;background:#fff}.plans-card{padding:13px 11px}.card-heading h2{margin:0;color:var(--m-copy);font-size:15px}.card-heading p{margin:7px 0 9px;color:var(--m-muted);font-size:10px}.plan-row{display:grid;grid-template-columns:minmax(0,1fr) 145px;gap:9px;width:100%;min-height:58px;padding:8px 11px;border:1px solid #e8eef5;border-radius:14px;background:#fff;text-align:left}.plan-row+.plan-row{margin-top:8px}.plan-row span,.plan-row strong,.plan-row small,.plan-progress b,.plan-progress em{display:block}.plan-row strong{overflow:hidden;color:var(--m-copy);font-size:12px;text-overflow:ellipsis;white-space:nowrap}.plan-row small{margin-top:6px;color:var(--m-muted);font-size:9px}.plan-progress{display:grid!important;grid-template-columns:1fr auto;align-content:center;gap:8px}.plan-progress b{color:var(--m-copy);font-size:10px;font-weight:500}.plan-progress em{color:var(--m-blue);font-size:10px;font-style:normal;font-weight:700}.plan-progress :deep(.nut-progress){grid-column:1/-1}.todo-card{margin-top:12px;padding:13px}.todo-actions{display:flex;gap:34px;margin:12px 0}.todo-actions button{min-height:44px;background:transparent;font-size:12px;font-weight:700}.todo-card>p{margin:0;color:var(--m-faint);font-size:10px;line-height:1.5}.ranking-tabs{margin-top:12px}.ranking-tabs :deep(.nut-tabs__titles){border-radius:14px;background:#edf2f8}.ranking-tabs :deep(.nut-tabs__titles-item){min-height:44px;font-size:11px}.ranking-empty{min-height:390px;margin-top:18px;padding:42px 18px;border:1px solid var(--m-line);border-radius:18px;background:#fff}:deep(.ranking-empty p),.ranking-note{color:var(--m-faint);font-size:10px;line-height:1.55;text-align:center}.mobile-search{margin:8px 0}.mobile-search :deep(.nut-searchbar){padding:0;background:transparent}.mobile-search :deep(.nut-searchbar__search-input){min-height:44px;border:1px solid var(--m-line);border-radius:14px;background:#f6f9fc}.filter-bar{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;width:100%;min-height:44px;margin:2px 0 12px;background:transparent}.filter-bar span{display:grid;place-items:center;border-radius:999px;color:var(--m-muted);background:#f2f5fa;font-size:10px}.learner-metrics{display:grid;grid-template-columns:repeat(4,1fr);margin-bottom:18px;padding:13px 10px;border:1px solid var(--m-line);border-radius:16px;background:#fff}.learner-metrics span{text-align:center}.learner-metrics strong,.learner-metrics small{display:block}.learner-metrics strong{font-size:18px}.learner-metrics small{margin-top:7px;color:var(--m-faint);font-size:9px}.learner-list,.review-list{overflow:hidden;padding:0 11px}.learner-list>button,.review-list>button{display:flex;align-items:center;gap:11px;width:100%;min-height:62px;border-bottom:1px solid var(--m-line);background:#fff;text-align:left}.learner-list>button:last-of-type,.review-list>button:last-of-type{border-bottom:0}.learner-list i,.review-list i{display:grid;flex:0 0 38px;place-items:center;width:38px;height:38px;border-radius:50%;color:var(--m-blue);background:#eef4ff;font-size:12px;font-style:normal;font-weight:700}.learner-list span,.review-list span{flex:1;min-width:0}.learner-list strong,.learner-list small,.review-list strong,.review-list small{display:block}.learner-list strong,.review-list strong{font-size:12px}.learner-list small,.review-list small{margin-top:5px;color:var(--m-faint);font-size:9px}.learner-list em{min-width:70px;padding:6px 10px;border-radius:999px;font-size:10px;font-style:normal;text-align:center}.learner-list em.warning{color:#be741b;background:#fff4e2}.learner-list em.neutral{color:#6f7c91;background:#edf2f8}.plan-hero{position:relative;min-height:108px;margin:14px 0 18px;padding:17px;border-radius:22px;color:#fff;background:var(--m-blue)}.plan-hero span,.plan-hero strong,.plan-hero small{display:block}.plan-hero span{font-size:11px}.plan-hero strong{margin:7px 0;font-size:30px}.plan-hero small{color:#dce9ff;font-size:10px}.plan-hero b{position:absolute;right:18px;top:18px;padding:7px 13px;border-radius:999px;color:var(--m-blue);background:#fff;font-size:10px}.plan-list{min-height:460px;padding:0 13px}.plan-list article{padding:15px 0;border-bottom:1px solid var(--m-line)}.plan-list article.paused{opacity:.72}.plan-list article>button{display:flex;justify-content:space-between;width:100%;min-height:44px;background:transparent;text-align:left}.plan-list article>button span{min-width:0}.plan-list strong,.plan-list small{display:block}.plan-list strong{color:var(--m-copy);font-size:13px}.plan-list small{margin-top:7px;color:var(--m-muted);font-size:9px}.plan-list article>button em{color:var(--m-blue);font-size:12px;font-style:normal;font-weight:700}.plan-list article>p{display:flex;align-items:center;justify-content:space-between;margin:9px 0 0;color:var(--m-muted);font-size:10px}.plan-list article>p b{color:#b06a1d}.plan-list article>p button{min-height:44px;color:var(--m-blue);background:transparent}.plan-rule{margin:18px 0;color:var(--m-faint);font-size:10px}.review-page{padding-bottom:34px}.review-header{display:flex;align-items:flex-start}.review-header>button{flex:0 0 34px;min-height:44px;margin-left:-10px;background:transparent;color:var(--m-copy);font-size:34px}.review-header .mobile-heading{flex:1}.review-summary{display:flex;align-items:center;gap:24px;margin-bottom:18px;padding:13px}.review-summary span{color:var(--m-muted);font-size:10px}.review-summary strong{display:block;margin-top:6px;color:#f58c1f;font-size:24px}.review-summary p{margin:0;color:var(--m-faint);font-size:10px}.review-list>button em{display:grid;gap:7px;color:var(--m-blue);font-size:10px;font-style:normal}.review-list>button em b{padding:6px 10px;border-radius:999px;color:#bb7119;background:#fff4e2;font-size:10px}.review-list u{text-decoration:none;color:var(--m-faint)}.review-entry{margin-top:45px;color:var(--m-muted);font-size:10px}.mobile-tabbar{position:fixed;z-index:30;right:16px;bottom:max(10px,env(safe-area-inset-bottom));left:16px;max-width:398px;margin:auto;overflow:hidden;border:1px solid var(--m-line);border-radius:24px;background:#fff;box-shadow:0 12px 36px #173a7418}.mobile-tabbar :deep(.nut-tabbar){position:static;min-height:62px;border:0}.mobile-tabbar :deep(.nut-tabbar-item){min-width:44px;min-height:56px}.mobile-error{position:fixed;z-index:40;right:16px;bottom:96px;left:16px;max-width:398px;margin:auto;padding:11px 14px;border-radius:12px;color:#a34d3a;background:#fff1eb;box-shadow:0 8px 28px #173a7425;font-size:11px}.mobile-error button{float:right;color:var(--m-blue);background:transparent}.sheet{width:min(100vw,430px);max-height:88dvh;margin:auto;overflow:auto;padding:20px 20px calc(22px + env(safe-area-inset-bottom));color:var(--m-ink);background:#fff}.sheet-heading{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:18px}.sheet-heading h2{margin:0;font-size:19px}.sheet-heading p{margin:7px 0 0;color:var(--m-faint);font-size:11px}.sheet-heading button{width:44px;height:44px;margin:-11px -11px 0 0;border-radius:50%;color:var(--m-faint);background:transparent;font-size:22px}.sheet-primary{width:100%;min-height:48px;margin-top:18px;border-radius:14px;color:#fff;background:var(--m-blue);font-weight:700}.sheet-primary:disabled{opacity:.55}.sheet-cell{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:58px;margin:10px 0;padding:10px 14px;border:1px solid var(--m-line);border-radius:14px;background:#fff;text-align:left}.sheet-cell.selected{border-color:#8cb7ff;background:#eef4ff}.sheet-cell strong,.sheet-cell small{display:block}.sheet-cell small{margin-top:5px;color:var(--m-faint);font-size:10px}.sheet-cell b{visibility:hidden;color:var(--m-blue)}.sheet-cell.selected b{visibility:visible}.sheet h3{margin:17px 0 9px;font-size:13px}.choice-grid{display:flex;flex-wrap:wrap;gap:9px}.choice-grid button{min-height:44px;padding:0 14px;border-radius:999px;color:var(--m-muted);background:#f2f5fa}.choice-grid button.selected{color:var(--m-blue);background:#e9f1ff}.switch-row{display:flex;align-items:center;justify-content:space-between;min-height:62px;padding:10px 0}.switch-row strong,.switch-row small{display:block}.switch-row small{margin-top:5px;color:var(--m-faint);font-size:10px}.switch-row input{width:44px;height:24px;accent-color:var(--m-blue)}.detail-rate span,.detail-rate strong{display:block}.detail-rate span{color:var(--m-muted);font-size:11px}.detail-rate strong{margin:7px 0;color:var(--m-blue);font-size:30px}.detail-states{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.detail-states span{padding:12px;border-radius:14px;background:#f6f9fc}.detail-states strong,.detail-states small{display:block}.detail-states strong{color:#21ad59;font-size:18px}.detail-states span:nth-child(2) strong{color:#f58c1f}.detail-states span:nth-child(3) strong{color:#eb3338}.detail-states small{margin-top:7px;color:var(--m-faint);font-size:9px}.plan-detail dl,.learner-detail{display:grid;grid-template-columns:1fr 1fr;gap:14px}.plan-detail dl div,.learner-detail div{min-width:0}.plan-detail dt,.learner-detail dt{color:var(--m-faint);font-size:10px}.plan-detail dd,.learner-detail dd{margin:6px 0 0;color:var(--m-copy);font-size:12px;font-weight:700}.capability-note{color:var(--m-muted);font-size:10px;line-height:1.6}.sheet-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px}.sheet-actions button{min-height:44px;border:1px solid var(--m-line);border-radius:12px;color:var(--m-copy);background:#fff;font-weight:700}.sheet-actions button.primary{color:#fff;border-color:var(--m-blue);background:var(--m-blue)}.readonly-field{display:grid;gap:6px;margin:12px 0;padding:14px;border:1px solid var(--m-line);border-radius:14px}.readonly-field span,.readonly-field small{color:var(--m-faint);font-size:10px}.readonly-field strong{font-size:13px}.ai-score{display:grid;grid-template-columns:1fr auto;align-items:center;padding:16px;border-radius:16px;background:#eef4ff}.ai-score span{grid-column:1/-1;color:var(--m-faint);font-size:10px}.ai-score strong{margin-top:7px;color:var(--m-blue);font-size:30px}.ai-score b{color:var(--m-muted);font-size:10px}.audio-state{display:grid;gap:10px;margin:18px 0;padding:14px;border:1px solid var(--m-line);border-radius:14px;background:#f6f9fc}.audio-state>div{display:flex;justify-content:space-between}.audio-state small{color:var(--m-faint);font-size:10px}.audio-state>button{width:44px;height:44px;border-radius:50%;color:#fff;background:var(--m-blue)}.audio-state :deep(.nut-audio){width:100%}.review-form{display:grid;grid-template-columns:110px 1fr;gap:12px}.review-form label{display:grid;gap:6px}.review-form label span{color:var(--m-copy);font-size:11px;font-weight:700}.review-form input,.review-form textarea{width:100%;min-height:44px;padding:10px;border:1px solid var(--m-line);border-radius:10px;resize:none}.inline-error{padding:10px;border-radius:10px;color:#a34d3a;background:#fff1eb;font-size:10px}.learner-detail{grid-template-columns:1fr}.learner-detail div{padding:13px;border-radius:12px;background:#f6f9fc}:deep(.nut-dialog){border-radius:22px}:deep(.nut-dialog__header){font-weight:700}:deep(.nut-dialog__footer-ok){background:var(--m-blue)}@media(max-width:370px){.mobile-page{padding-right:14px;padding-left:14px}.plan-row{grid-template-columns:1fr}.hero-card>small{white-space:normal}.review-form{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
.admin-mobile :deep(.mobile-heading p){margin:7px 0 10px;line-height:1.45}
.admin-mobile .hero-card{margin:6px 0 12px}
.admin-mobile .state-grid{margin-bottom:12px}
.admin-mobile .plans-card{padding:11px}
.admin-mobile .card-heading p{margin:5px 0 7px}
.admin-mobile .plan-row{min-height:50px;padding:6px 11px}
.admin-mobile .plan-row+.plan-row{margin-top:7px}
.admin-mobile .review-header>button{flex-basis:44px;width:44px}
.admin-mobile :deep(.nut-dialog__footer-cancel){color:var(--m-copy);border-color:#dbe6f5}
.learner-list em.success{color:#178a47;background:#eaf8ef}.learner-list em.active{color:#1463f2;background:#eef4ff}.learner-progress-sheet{min-height:min(76dvh,680px)}.learner-progress-skeleton{display:grid;gap:12px;margin-top:14px}.learner-progress-summary{margin-bottom:16px;padding:16px;border:1px solid var(--m-line);border-radius:18px;background:linear-gradient(145deg,#f7faff,#fff)}.learner-progress-summary>div:first-child{display:grid;grid-template-columns:1fr auto;align-items:end;margin-bottom:12px}.learner-progress-summary span{color:var(--m-muted);font-size:11px}.learner-progress-summary>div:first-child strong{grid-row:1/3;grid-column:2;color:var(--m-blue);font-size:30px;line-height:1}.learner-progress-summary>div:first-child small{margin-top:6px;color:var(--m-faint);font-size:10px}.learner-progress-kpis{display:grid!important;grid-template-columns:repeat(3,1fr)!important;gap:8px;margin-top:16px!important}.learner-progress-kpis span{padding:10px 6px;border-radius:12px;background:#f1f5fb;text-align:center}.learner-progress-kpis b,.learner-progress-kpis small{display:block}.learner-progress-kpis b{color:var(--m-copy);font-size:17px}.learner-progress-kpis small{margin-top:5px;color:var(--m-faint);font-size:9px}.learner-progress-list{display:grid;gap:12px}.learner-progress-card{padding:14px;border:1px solid var(--m-line);border-radius:16px;background:#fff}.learner-progress-card header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.learner-progress-card header div{min-width:0}.learner-progress-card header span,.learner-progress-card header strong{display:block}.learner-progress-card header span{color:var(--m-blue);font-size:9px;font-weight:700}.learner-progress-card header strong{margin-top:5px;overflow:hidden;color:var(--m-copy);font-size:13px;text-overflow:ellipsis;white-space:nowrap}.learner-progress-card header em{flex:0 0 auto;padding:6px 9px;border-radius:999px;font-size:9px;font-style:normal}.learner-progress-card header em.warning{color:#b86d16;background:#fff4e2}.learner-progress-card header em.success{color:#178a47;background:#eaf8ef}.learner-progress-card header em.active{color:#1463f2;background:#eef4ff}.learner-progress-card header em.neutral{color:#6f7c91;background:#edf2f8}.learner-progress-line{display:grid;grid-template-columns:1fr auto;align-items:center;gap:10px;margin:14px 0 12px}.learner-progress-line b{min-width:34px;color:var(--m-blue);font-size:11px;text-align:right}.learner-progress-card dl{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:0}.learner-progress-card dl div{min-width:0;padding:9px;border-radius:10px;background:#f6f9fc}.learner-progress-card dt{color:var(--m-faint);font-size:9px}.learner-progress-card dd{margin:5px 0 0;overflow:hidden;color:var(--m-copy);font-size:10px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}.learner-progress-card>p{margin:10px 0 0;color:var(--m-muted);font-size:10px;line-height:1.5}.learner-progress-feedback{padding:24px;border:1px solid #ffd8cf;border-radius:16px;background:#fff7f4;text-align:center}.learner-progress-feedback strong{color:#9f4734;font-size:14px}.learner-progress-feedback p{margin:8px 0 14px;color:#a76b5d;font-size:11px;line-height:1.55}.learner-progress-feedback button{min-width:112px;min-height:44px;border-radius:12px;color:#fff;background:var(--m-blue);font-weight:700}.learner-progress-note{margin:16px 2px 0;color:var(--m-faint);font-size:10px;line-height:1.6}
.admin-mobile button{cursor:pointer;touch-action:manipulation}.learner-list em.danger{color:#c83c42;background:#fff0f1}.task-roster-sheet{min-height:min(82dvh,720px)}.progress-state-grid,.roster-summary-grid{display:grid;gap:8px;margin-bottom:12px}.progress-state-grid{grid-template-columns:repeat(3,1fr)}.roster-summary-grid{grid-template-columns:repeat(4,1fr)}.progress-state-grid span,.roster-summary-grid span{padding:11px 6px;border-radius:13px;background:#f3f6fa;text-align:center}.progress-state-grid strong,.progress-state-grid small,.roster-summary-grid strong,.roster-summary-grid small{display:block}.progress-state-grid strong,.roster-summary-grid strong{color:var(--m-copy);font-size:19px}.progress-state-grid small,.roster-summary-grid small{margin-top:6px;color:var(--m-faint);font-size:9px}.roster-summary-grid .success strong{color:#21ad59}.roster-summary-grid .warning strong{color:#f58c1f}.roster-summary-grid .danger strong{color:#eb3338}.task-roster-list{overflow:hidden;border:1px solid var(--m-line);border-radius:16px;background:#fff}.task-roster-list article{display:flex;align-items:center;gap:10px;min-height:72px;padding:11px;border-bottom:1px solid var(--m-line)}.task-roster-list article:last-of-type{border-bottom:0}.task-roster-list article>i{display:grid;flex:0 0 38px;place-items:center;width:38px;height:38px;border-radius:50%;color:var(--m-blue);background:#eef4ff;font-size:12px;font-style:normal;font-weight:700}.task-roster-list article>div{flex:1;min-width:0}.task-roster-list article>div strong,.task-roster-list article>div small{display:block}.task-roster-list article>div strong{font-size:12px}.task-roster-list article>div small{margin:5px 0 8px;overflow:hidden;color:var(--m-faint);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.task-roster-list article>span{display:grid;justify-items:end;gap:7px}.task-roster-list article>span em{padding:5px 8px;border-radius:999px;font-size:9px;font-style:normal}.task-roster-list article>span em.success{color:#178a47;background:#eaf8ef}.task-roster-list article>span em.active{color:#1463f2;background:#eef4ff}.task-roster-list article>span em.neutral{color:#6f7c91;background:#edf2f8}.task-roster-list article>span b{color:var(--m-muted);font-size:9px;font-weight:600}
.learner-broadcast-section{margin-top:22px}.learner-broadcast-section>header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:10px}.learner-broadcast-section h3,.learner-broadcast-section p{margin:0}.learner-broadcast-section h3{font-size:14px}.learner-broadcast-section header p{margin-top:5px;color:var(--m-faint);font-size:10px}.learner-broadcast-section header>b{padding:6px 9px;border-radius:999px;color:var(--m-blue);background:#eef4ff;font-size:10px}.learner-broadcast-list{overflow:hidden;border:1px solid var(--m-line);border-radius:16px;background:#fff}.learner-broadcast-list>button{display:flex;align-items:center;gap:10px;width:100%;min-height:68px;padding:10px 12px;border-bottom:1px solid var(--m-line);background:#fff;text-align:left}.learner-broadcast-list>button:last-of-type{border-bottom:0}.learner-broadcast-list>button:disabled{cursor:default;opacity:.68}.learner-broadcast-list>button span{flex:1;min-width:0}.learner-broadcast-list strong,.learner-broadcast-list small{display:block}.learner-broadcast-list strong{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.learner-broadcast-list small{margin-top:6px;color:var(--m-faint);font-size:9px;line-height:1.4}.learner-broadcast-list em{padding:6px 8px;border-radius:999px;font-size:9px;font-style:normal}.learner-broadcast-list em.success{color:#178a47;background:#eaf8ef}.learner-broadcast-list em.warning{color:#b86d16;background:#fff4e2}.learner-broadcast-list em.active{color:#1463f2;background:#eef4ff}.learner-broadcast-list em.neutral{color:#6f7c91;background:#edf2f8}.learner-broadcast-list>button>b{color:var(--m-faint);font-size:17px}.learner-progress-feedback.compact{margin:10px 0;padding:16px}.learner-attempt-sheet{min-height:min(82dvh,720px)}.learner-score-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0}.learner-score-grid span{padding:11px 5px;border-radius:12px;background:#f3f6fa;text-align:center}.learner-score-grid small,.learner-score-grid strong{display:block}.learner-score-grid small{color:var(--m-faint);font-size:9px}.learner-score-grid strong{margin-top:6px;color:var(--m-copy);font-size:16px}.transcript-card,.issue-card,.teacher-review-card{margin-top:14px;padding:15px;border:1px solid var(--m-line);border-radius:16px;background:#fff}.transcript-card h3,.issue-card h3,.teacher-review-card h3{margin:0 0 8px;font-size:12px}.transcript-card h3:not(:first-child){margin-top:15px}.transcript-card p,.teacher-review-card p{margin:0;color:var(--m-muted);font-size:10px;line-height:1.7;white-space:pre-wrap}.issue-card h3{display:flex;justify-content:space-between}.issue-card h3 b{color:var(--m-blue)}.issue-card ul{display:grid;gap:9px;margin:0;padding:0;list-style:none}.issue-card li{padding:10px;border-radius:11px;background:#f6f9fc}.issue-card li strong,.issue-card li span{display:block}.issue-card li strong{font-size:10px}.issue-card li span{margin-top:5px;color:var(--m-muted);font-size:10px;line-height:1.5}.teacher-review-card>strong{display:block;margin-bottom:7px;color:var(--m-blue);font-size:12px}
</style>
