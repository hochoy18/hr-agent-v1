<template>
  <div class="smart-interview">
    <div class="page-container">
      <!-- 页面头部 -->
      <div class="page-header">
      <div class="header-content">
        <div class="header-left">
          <h1 class="page-title">
            <el-icon><VideoCamera /></el-icon>
            智能面试
          </h1>
          <p class="page-subtitle">
            AI辅助面试，提供智能问题推荐和候选人评估
          </p>
        </div>
        
        <!-- 筛选区域 -->
        <div class="filter-section">
          <div class="filter-row">
            <div class="filter-item">
              <label class="filter-label">姓名筛选</label>
              <el-input
                v-model="filters.name"
                placeholder="请输入候选人姓名"
                clearable
                size="default"
                style="width: 200px"
                @input="handleFilterChange"
              >
                <template #prefix>
                  <el-icon><Search /></el-icon>
                </template>
              </el-input>
            </div>
            
            <div class="filter-item">
              <label class="filter-label">岗位筛选</label>
              <el-select
                v-model="filters.position"
                placeholder="请选择岗位"
                clearable
                size="default"
                style="width: 200px"
                @change="handleFilterChange"
              >
                <el-option
                  v-for="position in availablePositions"
                  :key="position"
                  :label="position"
                  :value="position"
                />
              </el-select>
            </div>
            
            <div class="filter-actions">
              <el-button @click="clearFilters" size="default">
                <el-icon><RefreshLeft /></el-icon>
                重置筛选
              </el-button>
              <el-tag v-if="filteredCandidatesCount !== totalCandidatesCount" type="info" size="default">
                已筛选 {{ filteredCandidatesCount }} / {{ totalCandidatesCount }} 人
              </el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域：左右分栏布局 -->
    <div class="main-content">
      <!-- 左侧：候选人列表 -->
      <div class="left-panel">
        <el-card class="candidate-list-card">
          <template #header>
            <div class="card-header">
              <span>候选人列表</span>
              <el-button size="small" @click="refreshCandidates">
                <el-icon><Refresh /></el-icon>
                刷新
              </el-button>
            </div>
          </template>

          <div class="candidate-list">
            <div 
              v-for="candidate in filteredCandidates" 
              :key="candidate.id"
              class="candidate-item"
              :class="{ active: selectedCandidate?.id === candidate.id }"
              @click="selectCandidate(candidate)"
            >
              <!-- 候选人基本信息 -->
              <div class="candidate-info">
                <div class="candidate-header">
                  <h3 class="candidate-name">{{ candidate.name }}</h3>
                  <el-tag :type="getScoreType(candidate.totalScore)" size="small">
                    {{ candidate.totalScore }}分
                  </el-tag>
                </div>
                <p class="candidate-position">{{ candidate.position }}</p>
                <div class="candidate-details">
                  <span class="detail-item">{{ candidate.experience }}年经验</span>
                  <span class="detail-item">{{ candidate.education }}</span>
                  <span class="detail-item">{{ candidate.location }}</span>
                </div>
              </div>



              <!-- 操作按钮 -->
              <div class="candidate-actions">
                <el-button
                  size="small"
                  type="primary"
                  @click.stop="generateInterviewPlan(candidate)"
                  :loading="generatingPlan && selectedCandidate?.id === candidate.id"
                >
                  生成面试方案
                </el-button>
                <el-button size="small" @click.stop="viewResume(candidate)">
                  查看简历
                </el-button>
                <el-button size="small" type="danger" @click.stop="deleteInterviewPlanForCandidate(candidate)">
                  删除方案
                </el-button>
              </div>
            </div>
            
            <!-- 空状态 -->
            <div v-if="filteredCandidates.length === 0" class="empty-candidates">
              <el-empty 
                description="没有找到符合条件的候选人"
                :image-size="120"
              >
                <el-button type="primary" @click="clearFilters">
                  清除筛选条件
                </el-button>
              </el-empty>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右侧：Tab页内容 -->
      <div class="right-panel">
        <el-card class="content-card">
          <el-tabs v-model="activeTab" class="content-tabs" @tab-change="handleTabChange">
            <!-- 简历预览Tab -->
            <el-tab-pane label="简历预览" name="resume">
              <div class="resume-preview">
                <div v-if="!selectedCandidate" class="empty-state">
                  <el-empty description="请选择一个候选人查看简历" />
                </div>
                <div v-else class="resume-detail-content">
                  <!-- 详情头部 -->
                  <div class="detail-header">
                    <div class="candidate-profile">
                      <el-avatar :size="60" :src="selectedCandidate.avatar">
                        {{ selectedCandidate.name?.charAt(0) }}
                      </el-avatar>
                      <div class="profile-info">
                        <h3>{{ selectedCandidate.name }}</h3>
                        <p class="current-position">{{ selectedCandidate.position }}</p>
                        <div class="profile-meta">
                          <span class="meta-item">{{ selectedCandidate.experience }}</span>
                          <span class="meta-divider">|</span>
                          <span class="meta-item">{{ selectedCandidate.education }}</span>
                          <span class="meta-divider">|</span>
                          <span class="meta-item">{{ selectedCandidate.originalData?.candidate_age || '未知' }}岁</span>
                        </div>
                      </div>
                    </div>
                    <div class="score-section">
                      <div class="score-display">
                        <el-progress
                          type="circle"
                          :percentage="selectedCandidate.totalScore"
                          :color="getScoreColor(selectedCandidate.totalScore)"
                          :width="80"
                        >
                          <template #default="{ percentage }">
                            <span class="score-text">{{ percentage }}分</span>
                          </template>
                        </el-progress>
                      </div>
                      <p class="score-label">匹配度</p>
                    </div>
                  </div>

                  <!-- 详情主要内容 - 两列布局 -->
                  <div class="detail-main">
                    <div class="two-column-layout">
                      <!-- 左列：简历详情 -->
                      <div class="left-column">
                        <div class="column-header">
                          <h4 class="column-title">
                            <el-icon><Document /></el-icon>
                            简历详情
                          </h4>
                        </div>
                        <div class="column-content">
                          <div class="resume-content-section">
                            <div class="content-display" v-html="formattedResumeContent"></div>
                          </div>
                        </div>
                      </div>

                      <!-- 右列：评价结果 -->
                      <div class="right-column">
                        <div class="column-header">
                          <h4 class="column-title">
                            <el-icon><Star /></el-icon>
                            评价结果
                          </h4>
                        </div>
                        <div class="column-content">
                          <div class="evaluation-section">
                            <div v-if="selectedCandidate.originalData?.evaluation_metrics && selectedCandidate.originalData.evaluation_metrics.length > 0" class="evaluation-content">
                              <div
                                v-for="metric in selectedCandidate.originalData.evaluation_metrics"
                                :key="metric.name"
                                class="evaluation-item"
                              >
                                <div class="metric-header">
                                  <h4 class="metric-name">{{ metric.name }}</h4>
                                  <div class="metric-score">
                                    <el-tag :type="getMetricScoreType(metric.score, metric.max)">
                                      {{ metric.score }}/{{ metric.max }}分
                                    </el-tag>
                                  </div>
                                </div>
                                <div class="metric-reason">
                                  <p>{{ metric.reason }}</p>
                                </div>
                              </div>
                            </div>
                            <div v-else class="no-evaluation">
                              <el-empty description="暂无评价数据" :image-size="100" />
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- 面试方案预览Tab -->
            <el-tab-pane label="面试方案" name="interview-plan">
              <div class="interview-plan-preview">
                
                
                <div v-if="!selectedCandidate" class="empty-state">
                  <el-empty description="请选择一个候选人并生成面试方案" />
                </div>
                <div v-else-if="!interviewPlan" class="empty-state">
                    <el-empty description="暂无面试方案，请点击生成面试方案按钮" />
                  </div>
                <div v-else class="interview-plan-content">
                  <!-- 方案头部 -->
                  <div class="plan-header">
                    <div class="header-info">
                      <h2>{{ interviewPlan.candidateName }} - 面试方案</h2>
                      <p class="position">{{ interviewPlan.position }}</p>
                      <p class="generated-time">生成时间：{{ interviewPlan.generatedAt }}</p>
                    </div>
                    <div class="header-tags">
                      <el-tag type="success" size="large">AI自动生成</el-tag>
                      <el-tag v-if="interviewPlan.isGenerating" type="warning" size="large">
                        <el-icon class="is-loading"><Loading /></el-icon>
                        生成中...
                      </el-tag>
                      <el-tag v-if="isEditingPlan" type="info" size="large">编辑模式</el-tag>
                    </div>
                  </div>

                  <!-- 操作按钮 - 移到内容上方 -->
                  <div class="plan-actions">
                    <div class="action-group">
                      <!-- 生成后已自动保存；只在未保存或编辑中时提供手动保存 -->
                      <el-button 
                        v-if="interviewPlan.content && (!interviewPlan.isSaved || isEditingPlan)" 
                        type="success" 
                        @click="saveInterviewPlan" 
                        :loading="savingPlan"
                      >
                        <el-icon><DocumentAdd /></el-icon>
                        {{ isEditingPlan ? '保存修改' : '保存方案' }}
                      </el-button>
                      
                      <!-- 已保存状态提示 -->
                      <el-tag 
                        v-if="!isEditingPlan && interviewPlan.isSaved" 
                        type="success" 
                        size="large"
                      >
                        <el-icon><Check /></el-icon>
                        已保存
                      </el-tag>

                      <el-tag v-if="autoSavingPlan" type="warning" size="large">
                        <el-icon class="is-loading"><Loading /></el-icon>
                        自动保存中...
                      </el-tag>
                      
                      <el-button v-if="!isEditingPlan" type="primary" @click="toggleEditPlan">
                        <el-icon><Edit /></el-icon>
                        编辑方案
                      </el-button>
                      <el-button v-if="isEditingPlan" @click="cancelEditPlan">
                        <el-icon><Close /></el-icon>
                        取消编辑
                      </el-button>
                    </div>
                    <div class="action-group">
                      <!-- 已有有效会议时按钮切换为会议态，点击直接查看会议信息 -->
                      <el-tooltip
                        v-if="activeMeeting"
                        :content="activeMeetingTooltip"
                        placement="top"
                      >
                        <el-button
                          :type="activeMeetingPhase === 'ongoing' ? 'warning' : 'success'"
                          plain
                          @click="startInterview"
                          :disabled="isEditingPlan"
                          :loading="checkingMeeting"
                        >
                          <el-icon><Calendar /></el-icon>
                          {{ activeMeetingButtonText }}
                        </el-button>
                      </el-tooltip>
                      <el-button
                        v-else
                        type="primary"
                        @click="startInterview"
                        :disabled="isEditingPlan"
                        :loading="checkingMeeting"
                      >
                        <el-icon><VideoCamera /></el-icon>
                        开始面试
                      </el-button>
                      <el-dropdown @command="exportPlan" :disabled="isEditingPlan">
                        <el-button>
                          <el-icon><Download /></el-icon>
                          导出方案
                          <el-icon><ArrowDown /></el-icon>
                        </el-button>
                        <template #dropdown>
                          <el-dropdown-menu>
                            <el-dropdown-item command="txt">导出为TXT</el-dropdown-item>
                            <el-dropdown-item command="md">导出为Markdown</el-dropdown-item>
                          </el-dropdown-menu>
                        </template>
                      </el-dropdown>
                      <el-button @click="regeneratePlan" :loading="generatingPlan" :disabled="isEditingPlan">
                        <el-icon><Refresh /></el-icon>
                        重新生成
                      </el-button>
                    </div>
                  </div>

                  <!-- 面试方案内容 -->
                  <div class="plan-section">
                    <!-- 编辑模式 -->
                    <div v-if="isEditingPlan" class="edit-container">
                      <el-input
                        v-model="editPlanContent"
                        type="textarea"
                        :rows="20"
                        placeholder="在此编辑面试方案内容..."
                        class="edit-textarea"
                      />
                    </div>
                    <!-- 预览模式 -->
                    <div v-else class="plan-content markdown-content" v-html="formattedInterviewPlan"></div>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <!-- 面试记录Tab -->
            <el-tab-pane label="面试记录" name="interview-records">
              <div class="interview-records">
                <div v-if="!selectedCandidate" class="empty-state">
                  <el-empty description="请选择一个候选人查看面试记录" />
                </div>
                <div v-else>
                  <div class="records-toolbar">
                    <span class="records-title">{{ selectedCandidate.name }} 的面试记录</span>
                    <el-button size="small" :loading="loadingRecords" @click="fetchInterviewRecords">刷新</el-button>
                  </div>

                  <div v-if="interviewRecords.length === 0 && !loadingRecords" class="empty-state">
                    <el-empty description="暂无面试记录，请先在面试方案页点击开始面试" />
                  </div>

                  <div v-for="record in interviewRecords" :key="record.id" class="record-card">
                    <div class="record-header">
                      <div>
                        <h4>{{ record.subject }}</h4>
                        <p class="record-time">
                          {{ formatDateTime(record.start_time) }} ~ {{ formatDateTime(record.end_time) }}
                        </p>
                        <p class="record-candidate">
                          候选人：
                          <span v-if="record.candidate_name">{{ record.candidate_name }}</span>
                          <el-tag v-else size="small" type="warning" effect="plain">未填写</el-tag>
                          <el-button link type="primary" size="small" @click="openCandidateDialog(record)">
                            {{ record.candidate_name ? '修改' : '填写' }}
                          </el-button>
                        </p>
                      </div>
                      <div class="record-tags">
                        <el-tag :type="meetingTagType(meetingPhase(record))" size="small">
                          {{ meetingStatusLabel(meetingPhase(record)) }}
                        </el-tag>
                        <el-tag :type="analysisTagType(record.analysis_status)" size="small">
                          {{ analysisDisplayLabel(record) }}
                        </el-tag>
                      </div>
                    </div>

                    <div v-if="record.join_url" class="record-meeting">
                      <span class="meeting-code">会议号：{{ record.meeting_code || '-' }}</span>
                      <el-button link type="primary" size="small" @click="copyText(record.join_url)">复制入会链接</el-button>
                      <el-button v-if="record.password" link size="small" @click="copyText(record.password)">
                        复制密码（{{ record.password }}）
                      </el-button>
                    </div>

                    <div class="record-actions">
                      <el-upload
                        :show-file-list="false"
                        :auto-upload="false"
                        :on-change="(file) => handleMediaSelected(record, file)"
                      >
                        <el-button size="small" :loading="uploadingId === record.id">上传面试录音/视频/文档</el-button>
                      </el-upload>
                      <el-button
                        size="small"
                        :loading="pullingId === record.id"
                        :disabled="record.meeting_status === 'cancelled'"
                        @click="pullTencentTranscript(record)"
                      >
                        拉取腾讯会议转写
                      </el-button>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="analyzingId === record.id || record.analysis_status === 'analyzing'"
                        :disabled="!record.transcript || record.analysis_status === 'transcribing'"
                        @click="reanalyze(record)"
                      >
                        {{ analysisButtonText(record) }}
                      </el-button>
                      <el-button
                        size="small"
                        :loading="syncingId === record.id"
                        :disabled="!record.meeting_id || record.meeting_status === 'cancelled'"
                        @click="syncMeetingStatus(record)"
                      >
                        同步会议状态
                      </el-button>
                      <el-button
                        size="small"
                        :disabled="meetingPhase(record) !== 'scheduled'"
                        @click="openEditMeeting(record)"
                      >
                        修改会议
                      </el-button>
                      <el-button
                        size="small"
                        type="danger"
                        :disabled="!['scheduled', 'ongoing'].includes(meetingPhase(record))"
                        @click="cancelInterviewRecord(record)"
                      >
                        取消会议
                      </el-button>
                    </div>

                    <el-alert
                      v-if="record.error_message"
                      :title="record.error_message"
                      type="error"
                      :closable="false"
                      show-icon
                      class="record-error"
                    />

                    <el-alert
                      v-if="record.analysis_status === 'transcribing'"
                      title="正在转写面试内容，完成后会自动开始 AI 分析，请勿重复操作"
                      type="warning"
                      :closable="false"
                      show-icon
                      class="record-progress"
                    />
                    <el-alert
                      v-else-if="record.analysis_status === 'analyzing'"
                      title="AI 正在分析面试转写内容，通常需要 1~2 分钟，完成后自动刷新结果，请勿重复点击"
                      type="warning"
                      :closable="false"
                      show-icon
                      class="record-progress"
                    />

                    <div v-if="record.evaluation" class="evaluation-card">
                      <div class="evaluation-header">
                        <span class="evaluation-score">{{ record.evaluation.total_score }}<small>分</small></span>
                        <div class="evaluation-actions">
                          <el-tag :type="recommendationType(record.evaluation.recommendation)" size="large">
                            {{ record.evaluation.recommendation }}
                          </el-tag>
                          <el-button size="small" :icon="Edit" @click="openScoreEditor(record)">
                            修订分数
                          </el-button>
                        </div>
                      </div>
                      <div v-if="record.evaluation.manual_override" class="evaluation-manual">
                        本结果已人工修订 {{ record.evaluation.manual_override.count }} 次，AI 原总分
                        {{ record.evaluation.manual_override.original_total_score }} 分；最近一次修订原因：
                        <span class="manual-note" :title="lastOverrideNote(record)">{{
                          lastOverrideNote(record)
                        }}</span>
                      </div>
                      <el-table
                        v-if="record.evaluation.dimensions && record.evaluation.dimensions.length"
                        :data="record.evaluation.dimensions"
                        size="small"
                        class="evaluation-table"
                      >
                        <el-table-column prop="name" label="维度" width="140" />
                        <el-table-column label="得分" width="140">
                          <template #default="{ row }">
                            <span>{{ row.score }}/{{ row.max }}</span>
                            <el-tooltip
                              v-if="row.manual"
                              placement="top"
                              :content="`AI 原分 ${row.ai_score}，此处为人工修订值`"
                            >
                              <el-tag size="small" type="warning" effect="plain" class="manual-tag">
                                人工
                              </el-tag>
                            </el-tooltip>
                          </template>
                        </el-table-column>
                        <el-table-column prop="reason" label="评分理由" />
                      </el-table>
                      <p class="evaluation-summary">{{ record.evaluation.summary }}</p>
                      <div class="evaluation-lists">
                        <div>
                          <strong>优势</strong>
                          <ul>
                            <li v-for="(item, idx) in record.evaluation.strengths" :key="'s' + idx">{{ item }}</li>
                          </ul>
                        </div>
                        <div>
                          <strong>风险</strong>
                          <ul>
                            <li v-for="(item, idx) in record.evaluation.risks" :key="'r' + idx">{{ item }}</li>
                          </ul>
                        </div>
                      </div>
                      <div
                        v-if="record.evaluation.insufficient && record.evaluation.notes && record.evaluation.notes.length"
                        class="evaluation-insufficient"
                      >
                        <strong>为什么是「待定」</strong>
                        <ul>
                          <li v-for="(note, idx) in record.evaluation.notes" :key="'n' + idx">{{ note }}</li>
                        </ul>
                      </div>
                    </div>

                    <div v-else-if="record.transcript" class="transcript-preview">
                      <p class="transcript-title">转写预览</p>
                      <p class="transcript-text">
                        {{ record.transcript.slice(0, 300) }}{{ record.transcript.length > 300 ? '...' : '' }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </div>
    </div>

    <!-- 创建面试对话框 -->
    <el-dialog
      v-model="showCreateDialog"
      title="创建面试（腾讯会议）"
      width="620px"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="110px"
      >
        <el-form-item label="候选人">
          <el-input :model-value="selectedCandidate?.name" disabled />
        </el-form-item>

        <el-form-item label="应聘岗位">
          <el-input :model-value="selectedCandidate?.position" disabled />
        </el-form-item>

        <el-form-item label="会议主题" prop="subject">
          <el-input v-model="createForm.subject" placeholder="面试会议主题" maxlength="100" />
        </el-form-item>

        <el-form-item label="面试时间" prop="timeRange">
          <el-date-picker
            v-model="createForm.timeRange"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm"
            value-format="x"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="会议密码">
          <el-input v-model="createForm.password" placeholder="可选，4~6 位数字" maxlength="6" />
        </el-form-item>

        <el-form-item label="等候室">
          <el-switch v-model="createForm.autoInWaitingRoom" />
          <span class="form-hint">开启后候选人先进入等候室，由面试官放行</span>
        </el-form-item>

        <el-form-item label="云录制">
          <el-switch v-model="createForm.autoRecord" />
          <span class="form-hint">会议开始后自动云录制并生成逐字稿，供面试后 AI 评估使用</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creatingInterview" @click="createInterview">
          创建会议
        </el-button>
      </template>
    </el-dialog>

    <!-- 会议信息 -->
    <el-dialog v-model="showMeetingResult" title="面试会议信息" width="600px">
      <div v-if="createdMeeting" class="meeting-result">
        <p class="result-subject">{{ createdMeeting.subject }}</p>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="会议号">{{ createdMeeting.meeting_code || '-' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(createdMeeting.start_time) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(createdMeeting.end_time) }}</el-descriptions-item>
          <el-descriptions-item label="会议密码">{{ createdMeeting.password || '无' }}</el-descriptions-item>
          <el-descriptions-item label="入会链接">
            <span class="join-url">{{ createdMeeting.join_url }}</span>
          </el-descriptions-item>
        </el-descriptions>
        <div class="result-actions">
          <el-button type="primary" @click="copyText(createdMeeting.join_url)">复制候选人入会链接</el-button>
          <el-button @click="copyMeetingInfo">复制全部会议信息</el-button>
          <el-button
            v-if="meetingPhase(createdMeeting) === 'scheduled'"
            @click="openEditMeeting(createdMeeting)"
          >
            修改会议
          </el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="showMeetingResult = false">关闭</el-button>
        <el-button type="primary" @click="viewInterviewRecords">查看面试记录</el-button>
      </template>
    </el-dialog>

    <!-- 修改会议 -->
    <el-dialog v-model="showEditDialog" title="修改面试会议" width="620px">
      <el-form
        ref="editFormRef"
        :model="editForm"
        :rules="createRules"
        label-width="110px"
      >
        <el-form-item label="会议主题" prop="subject">
          <el-input v-model="editForm.subject" placeholder="面试会议主题" maxlength="100" />
        </el-form-item>

        <el-form-item label="面试时间" prop="timeRange">
          <el-date-picker
            v-model="editForm.timeRange"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            format="YYYY-MM-DD HH:mm"
            value-format="x"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="会议密码">
          <el-input v-model="editForm.password" placeholder="可选，4~6 位数字" maxlength="6" />
        </el-form-item>

        <el-form-item label="等候室">
          <el-switch v-model="editForm.autoInWaitingRoom" />
        </el-form-item>

        <el-form-item label="云录制">
          <el-switch v-model="editForm.autoRecord" />
          <span class="form-hint">会议开始后自动云录制并生成逐字稿，供面试后 AI 评估使用</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingMeeting" @click="saveMeetingEdit">
          保存修改
        </el-button>
      </template>
    </el-dialog>

    <!-- 人工修订面试评分 -->
    <el-dialog v-model="showScoreDialog" title="修订面试评分" width="640px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="score-alert"
        title="修订只改分数，不改 AI 的判定标签。AI 原分与修订原因会留在报告里，可随时对照。"
      />
      <el-table :data="scoreForm.dimensions" size="small" class="score-table">
        <el-table-column prop="name" label="维度" width="140" />
        <el-table-column label="AI 分" width="90">
          <template #default="{ row }">{{ row.ai_score }}/4</template>
        </el-table-column>
        <el-table-column label="修订为" width="150">
          <template #default="{ row }">
            <el-input-number
              v-model="row.score"
              :min="0"
              :max="4"
              :step="1"
              step-strictly
              size="small"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.score !== row.original" size="small" type="warning" effect="plain">
              已改动
            </el-tag>
            <span v-else class="score-unchanged">未改动</span>
          </template>
        </el-table-column>
      </el-table>

      <el-form label-width="90px" class="score-form">
        <el-form-item label="推荐结论">
          <el-select v-model="scoreForm.recommendation" style="width: 180px">
            <el-option label="推荐" value="推荐" />
            <el-option label="待定" value="待定" />
            <el-option label="不推荐" value="不推荐" />
          </el-select>
          <span class="form-hint">总分变了，原结论可能不再匹配，可一并调整</span>
        </el-form-item>
        <el-form-item label="修订原因" required>
          <el-input
            v-model="scoreForm.note"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="例：第 12 组回答里报了并发量和准确率，AI 只判成 claim，事实信息量偏低"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showScoreDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingScores" @click="saveScoreOverride">
          保存修订
        </el-button>
      </template>
    </el-dialog>

    <!-- 上传前确认候选人姓名 -->
    <el-dialog v-model="showUploadDialog" title="上传面试材料" width="560px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="upload-alert"
        title="AI 靠姓名在转写里认出谁在回答。姓名与转写中的说话人名称不一致时，只能由模型按内容猜，评分可能落到面试官身上。"
      />
      <el-form label-width="100px" class="upload-form">
        <el-form-item label="文件">
          <span class="upload-filename">{{ uploadForm.filename }}</span>
        </el-form-item>
        <el-form-item label="候选人姓名">
          <el-input
            v-model="uploadForm.candidateName"
            maxlength="100"
            placeholder="如：伍双林，需与转写中的说话人名称一致"
            clearable
          />
          <span class="form-hint">留空则沿用记录上已有的姓名</span>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" :loading="uploadingId === uploadForm.recordId" @click="confirmUpload">
          上传并转写
        </el-button>
      </template>
    </el-dialog>

    <!-- 修改 / 填写候选人姓名 -->
    <el-dialog v-model="showCandidateDialog" title="指定候选人姓名" width="520px">
      <el-form label-width="100px" class="candidate-form">
        <el-form-item label="候选人姓名">
          <el-input
            v-model="candidateForm.candidateName"
            maxlength="100"
            placeholder="如：伍双林，需与转写中的说话人名称一致"
            clearable
          />
        </el-form-item>
        <el-form-item label="转写中的称呼">
          <span class="form-hint candidate-hint">
            姓名会与转写里的说话人标签逐一比对（完全一致 → 互相包含 → 相似度 ≥0.6）。对不上时，
            AI 会按对话内容猜谁在回答，并在报告里标明「未经人工确认」。
          </span>
        </el-form-item>
        <el-alert
          v-if="candidateForm.hasEvaluation"
          type="warning"
          :closable="false"
          show-icon
          title="改名会作废当前评价"
          description="已有评分是按原姓名算出的，改名后会被清空，需要重新分析（转写已保留，不用重传文件）。"
        />
      </el-form>

      <template #footer>
        <el-button @click="showCandidateDialog = false">取消</el-button>
        <el-button type="primary" :loading="savingCandidate" @click="saveCandidateName">保存</el-button>
      </template>
    </el-dialog>

    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoCamera,
  Calendar,
  Search,
  Edit,
  Check,
  Close,
  DocumentAdd,
  Loading,
  Download,
  ArrowDown
} from '@element-plus/icons-vue'
import { resumeApi } from '@/api/resume'
import { hrWorkflowsApi } from '@/api/hrWorkflows'
import { interviewApi } from '@/api/interview'
import { marked } from 'marked'

// 响应式数据
const activeTab = ref('resume')
const selectedCandidate = ref(null)
const generatingPlan = ref(false)
const interviewPlan = ref(null)

// 编辑相关数据
const isEditingPlan = ref(false)
const editPlanContent = ref('')
const savingPlan = ref(false)
const autoSavingPlan = ref(false)
const originalPlanContent = ref('')

// 面试会议与面试记录
const showCreateDialog = ref(false)
const creatingInterview = ref(false)
const createFormRef = ref(null)
const createForm = reactive({
  subject: '',
  timeRange: [],
  password: '',
  autoInWaitingRoom: true,
  autoRecord: true
})
const createRules = {
  subject: [{ required: true, message: '请输入会议主题', trigger: 'blur' }],
  timeRange: [{ type: 'array', required: true, message: '请选择面试开始和结束时间', trigger: 'change' }]
}
const createdMeeting = ref(null)
const showMeetingResult = ref(false)
const showEditDialog = ref(false)
const savingMeeting = ref(false)
const editFormRef = ref(null)
const editForm = reactive({
  id: null,
  subject: '',
  timeRange: [],
  password: '',
  autoInWaitingRoom: true,
  autoRecord: true
})
const interviewRecords = ref([])
// 当前候选人的有效面试会议（未取消、未结束），用于控制「开始面试」按钮的状态
const candidateMeeting = ref(null)
const checkingMeeting = ref(false)
const nowMs = ref(Date.now())
let clockTimer = null
const loadingRecords = ref(false)
const uploadingId = ref(null)
const pullingId = ref(null)
const analyzingId = ref(null)
const syncingId = ref(null)
let recordPollingTimer = null

// 上传前确认候选人姓名：姓名决定 AI 在转写里认谁，填错会认到面试官头上
const showUploadDialog = ref(false)
const uploadForm = reactive({ recordId: null, filename: '', candidateName: '', file: null })

// 分析前后都能改姓名；改名会作废旧评价，需要重新分析
const showCandidateDialog = ref(false)
const savingCandidate = ref(false)
const candidateForm = reactive({ recordId: null, candidateName: '', hasEvaluation: false })

// 筛选相关数据
const filters = reactive({
  name: '',
  position: '',
  status: 'interview' // 默认只显示面试状态的简历
})

// 加载状态
const loading = ref(false)

// 候选人数据
const candidates = ref([])

// 计算属性
const availablePositions = computed(() => {
  const positions = [...new Set(candidates.value.map(c => c.position))]
  return positions.sort()
})

const filteredCandidates = computed(() => {
  return candidates.value.filter(candidate => {
    const nameMatch = !filters.name || 
      candidate.name.toLowerCase().includes(filters.name.toLowerCase())
    
    const positionMatch = !filters.position || 
      candidate.position === filters.position
    
    return nameMatch && positionMatch
  })
})

const filteredCandidatesCount = computed(() => filteredCandidates.value.length)
const totalCandidatesCount = computed(() => candidates.value.length)

// 格式化简历内容
const formattedResumeContent = computed(() => {
  if (!selectedCandidate.value?.originalData?.resume_content) return ''
  return marked(selectedCandidate.value.originalData.resume_content)
})

// 格式化面试方案内容
const formattedInterviewPlan = computed(() => {
  if (!interviewPlan.value?.content) return ''
  
  // 清理内容，移除可能包含的SSE事件数据
  let cleanedContent = interviewPlan.value.content
  
  // 如果内容包含workflow_started等事件数据，记录警告并返回空内容
  if (cleanedContent.includes('"event": "workflow_started"') || 
      cleanedContent.includes('"conversation_id"') ||
      cleanedContent.includes('"message_id"')) {
    console.warn('面试方案内容包含SSE事件数据，需要清理:', cleanedContent)
    return marked('正在生成面试方案，请稍候...')
  }
  
  return marked(cleanedContent)
})

// 当前候选人是否已有有效会议（未取消、未结束）
const activeMeeting = computed(() => {
  const meeting = candidateMeeting.value
  if (!meeting) return null
  if (['cancelled', 'completed'].includes(meeting.meeting_status)) return null
  const end = new Date(meeting.end_time).getTime()
  if (!Number.isNaN(end) && nowMs.value >= end) return null
  return meeting
})

const activeMeetingPhase = computed(() => (activeMeeting.value ? meetingPhase(activeMeeting.value) : null))

const activeMeetingButtonText = computed(() => {
  if (!activeMeeting.value) return '开始面试'
  return activeMeetingPhase.value === 'ongoing' ? '面试进行中' : '查看面试会议'
})

const activeMeetingTooltip = computed(() => {
  const meeting = activeMeeting.value
  if (!meeting) return ''
  const phaseText = activeMeetingPhase.value === 'ongoing' ? '面试进行中' : '已预约会议'
  return `${phaseText}：${formatDateTime(meeting.start_time)} ~ ${formatDateTime(meeting.end_time)}｜会议号 ${meeting.meeting_code || '-'}｜点击查看会议信息`
})

// 方法
const getScoreType = (score) => {
  if (score >= 90) return 'success'
  if (score >= 80) return 'warning'
  if (score >= 70) return 'info'
  return 'danger'
}

const getScoreColor = (score) => {
  if (score >= 90) return '#67c23a'
  if (score >= 80) return '#e6a23c'
  if (score >= 70) return '#409eff'
  return '#f56c6c'
}

const getMetricScoreType = (score, max) => {
  const percentage = (score / max) * 100
  if (percentage >= 80) return 'success'
  if (percentage >= 60) return 'warning'
  if (percentage >= 40) return 'info'
  return 'danger'
}

// 获取简历数据
const fetchCandidates = async () => {
  try {
    loading.value = true
    const response = await resumeApi.getResumeHistory({
      status: filters.status,
      limit: 100 // 获取更多数据
    })

    // 转换数据格式以适配现有的UI
    let mappedCandidates = response.items.map(resume => {
      // 从evaluation_metrics中提取评分数据
      const getMetricScore = (metricName) => {
        if (!resume.evaluation_metrics || !Array.isArray(resume.evaluation_metrics)) {
          return 0
        }
        const metric = resume.evaluation_metrics.find(m => m.name === metricName)
        if (!metric) return 0
        // 将分数转换为5分制（假设max为25分）
        return Math.min(5, Math.max(0, Math.round((metric.score / metric.max) * 5)))
      }

      return {
        id: resume.id,
        name: resume.candidate_name || '未知',
        // 面试岗位以在招 JD 为准，简历自述职位仅作兜底
        position: resume.job_title || resume.candidate_position || '未知职位',
        experience: resume.work_years || '未知',
        education: resume.education_level || '未知',
        location: '未知', // 简历数据中没有地址信息
        totalScore: resume.total_score || 0,
        status: resume.status,
        scores: {
         // 动态生成评分维度映射
          ...(() => {
            const dynamicScores = {}
            if (resume.evaluation_metrics && Array.isArray(resume.evaluation_metrics)) {
              resume.evaluation_metrics.forEach(metric => {
                // 使用维度名称作为key，转换为camelCase格式
                const key = metric.name.replace(/匹配度|经验|背景|技能|素质/g, '')
                  .replace(/^[A-Z]/, m => m.toLowerCase())
                  .replace(/[-_\s]+(.)?/g, (_, c) => c ? c.toUpperCase() : '')
                dynamicScores[key] = Math.min(5, Math.max(0, Math.round((metric.score / metric.max) * 5)))
              })
            }
            return dynamicScores
          })()
        },
        // 保存原始评价维度数据用于详细展示
        evaluationMetrics: resume.evaluation_metrics || [],
        // 只显示五大类评价维度：学历、工作经验、技能、项目经验、综合素质
        fiveMajorMetrics: (() => {
          if (!resume.evaluation_metrics || !Array.isArray(resume.evaluation_metrics)) {
            return []
          }
          
          // 定义五大类关键词映射
          const categoryKeywords = {
            '学历': ['学历', '教育', '学位', '学历匹配度'],
            '工作经验': ['工作经验', '工作经历', '经验', '工作经验匹配度'],
            '技能': ['技能', '技术', '能力', '技能匹配度'],
            '项目经验': ['项目', '项目经验', '项目经历', '项目经验匹配度'],
            '综合素质': ['综合素质', '综合能力', '素质', '综合匹配度']
          }
          
          // 筛选出属于五大类的评价维度
          const majorMetrics = []
          const processedCategories = new Set()
          
          // 遍历所有评价维度，找到属于五大类的维度
          resume.evaluation_metrics.forEach(metric => {
            const metricName = metric.name
            
            // 检查是否属于五大类
            for (const [category, keywords] of Object.entries(categoryKeywords)) {
              if (keywords.some(keyword => metricName.includes(keyword))) {
                // 如果这个类别还没有处理过，添加它
                if (!processedCategories.has(category)) {
                  majorMetrics.push({
                    name: category,
                    score: metric.score,
                    max: metric.max,
                    reason: metric.reason
                  })
                  processedCategories.add(category)
                }
                return
              }
            }
          })
          
          // 如果没有匹配到任何类别，返回原始数据的前5项
          if (majorMetrics.length === 0) {
            return resume.evaluation_metrics.slice(0, 5)
          }
          
          return majorMetrics
        })(),
        resume: {
          personalInfo: {
            name: resume.candidate_name || '未知',
            age: resume.candidate_age || '未知',
            phone: '***',
            email: '***',
            location: '未知'
          },
          workExperience: [],
          education: [],
          skills: [],
          content: resume.resume_content || ''
        },
        originalData: resume, // 保存原始数据
        updatedAt: resume.updated_at // 添加更新时间用于排序
      }
    })

    // 按更新时间倒序排列，确保最新更新为interview状态的候选人排在前面
    mappedCandidates.sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))

    candidates.value = mappedCandidates

  } catch (error) {
    console.error('获取候选人数据失败:', error)
    ElMessage.error('获取候选人数据失败')
  } finally {
    loading.value = false
  }
}

// 删除面试方案
const deleteInterviewPlanForCandidate = async (candidate) => {
  try {
    // 先查询该候选人是否有面试方案
    const response = await hrWorkflowsApi.getInterviewPlanList({
      resume_evaluation_id: candidate.id,
      limit: 1
    })

    if (!response || !response.items || response.items.length === 0) {
      ElMessage.warning('该候选人暂无面试方案')
      return
    }

    const planId = response.items[0].id

    await ElMessageBox.confirm(
      `确定要删除候选人 "${candidate.name}" 的面试方案吗？此操作不可撤销。`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )

    await hrWorkflowsApi.deleteInterviewPlan(planId)

    // 如果当前正在查看此候选人的面试方案，清除显示
    if (selectedCandidate.value?.id === candidate.id) {
      interviewPlan.value = null
    }

    ElMessage.success('面试方案删除成功')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.error('删除面试方案失败:', error)
      ElMessage.error('删除面试方案失败')
    }
  }
}

const selectCandidate = async (candidate) => {
  // 如果选择的是同一个候选人，不需要重新加载
  if (selectedCandidate.value?.id === candidate.id) {
    console.log('选择了同一个候选人，不重新加载面试方案')
    return
  }
  
  selectedCandidate.value = candidate
  activeTab.value = 'resume'
  // 清除之前的面试方案与面试记录
  interviewPlan.value = null
  stopRecordPolling()
  interviewRecords.value = []
  candidateMeeting.value = null
  
  // 检查是否已有保存的面试方案
  try {
    console.log('开始获取面试方案，候选人ID:', candidate.id)
    const response = await hrWorkflowsApi.getInterviewPlanList({
      resume_evaluation_id: candidate.id,
      limit: 1
    })
    
    console.log('API响应:', response)
    console.log('响应数据:', response)
    
    if (response && response.items && response.items.length > 0) {
      const savedPlan = response.items[0]
      console.log('找到已保存的面试方案:', savedPlan)
      console.log('候选人信息:', candidate)
      interviewPlan.value = {
        id: savedPlan.id,
        candidateId: candidate.id,
        candidateName: savedPlan.candidate_name || candidate.name,
        position: savedPlan.candidate_position || candidate.position,
        title: savedPlan.title,
        content: savedPlan.content,
        status: savedPlan.status,
        createdAt: savedPlan.created_at,
        updatedAt: savedPlan.updated_at,
        isGenerating: false,
        isSaved: true
      }
      console.log('设置的面试方案对象:', interviewPlan.value)
      console.log('当前activeTab:', activeTab.value)
      // 切换到面试方案标签页
      activeTab.value = 'interview-plan'
      console.log('切换后activeTab:', activeTab.value)
      ElMessage.success(`已选择候选人：${candidate.name}，发现已保存的面试方案`)
    } else {
      ElMessage.success(`已选择候选人：${candidate.name}`)
    }
  } catch (error) {
    console.error('检查面试方案失败:', error)
    console.error('错误详情:', error.message)
    console.error('错误堆栈:', error.stack)
    ElMessage.success(`已选择候选人：${candidate.name}`)
  }

  // 同步该候选人的会议状态，决定「开始面试」按钮显示为开始还是查看会议
  fetchCandidateMeeting(candidate.id)
}

const refreshCandidates = async () => {
  await fetchCandidates()
  ElMessage.success('候选人列表已刷新')
}

const viewResume = (candidate) => {
  selectCandidate(candidate)
  activeTab.value = 'resume'
}

const generateInterviewPlan = async (candidate) => {
  try {
    // 重新生成时要沿用该候选人已保存方案的 id，避免每次生成都新建一条重复记录
    const existingPlanId = interviewPlan.value?.candidateId === candidate.id
      ? (interviewPlan.value?.id || null)
      : null
    if (selectedCandidate.value?.id !== candidate.id) {
      candidateMeeting.value = null
    }
    selectedCandidate.value = candidate
    generatingPlan.value = true
    activeTab.value = 'interview-plan'
    fetchCandidateMeeting(candidate.id)
    
    // 清空之前的面试方案
    interviewPlan.value = null
    
    ElMessage.info('正在生成面试方案，请稍候...')
    
    // 调用新的API生成面试方案
    const response = await hrWorkflowsApi.generateInterviewPlanByResume({
      resume_id: candidate.id,
      stream: true
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    // 处理流式响应（缓冲分片并过滤控制事件）
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let planContent = ''
    let buffer = ''

    // 初始化面试方案对象
    interviewPlan.value = {
      id: existingPlanId,
      candidateId: candidate.id,
      candidateName: candidate.name,
      position: candidate.position,
      generatedAt: new Date().toLocaleString(),
      content: '',
      isGenerating: true,
      isSaved: false
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // 按流式方式解码并累积到缓冲区，避免半截JSON被渲染
        buffer += decoder.decode(value, { stream: true })

        // 事件以"\n\n"分隔，逐个消费完整事件块
        let sepIndex = buffer.indexOf('\n\n')
        while (sepIndex !== -1) {
          const eventChunk = buffer.slice(0, sepIndex)
          buffer = buffer.slice(sepIndex + 2)
          sepIndex = buffer.indexOf('\n\n')

          const lines = eventChunk.split('\n')
          for (const line of lines) {
            const l = line.trim()
            if (!l) continue

            // 调试：输出原始行数据
            if (l.startsWith('data:')) {
              console.log('原始SSE数据行:', l)
            }

            if (l.startsWith('event:') || l.startsWith('id:') || l.startsWith('retry:')) continue
            if (!l.startsWith('data: ')) continue

            const dataStr = l.slice(6).trim()
            if (!dataStr) continue
            if (dataStr === '[DONE]') break
            const lowerData = dataStr.toLowerCase()
            if (lowerData === 'ping' || lowerData.startsWith('event: ping')) continue

            try {
              const parsed = JSON.parse(dataStr)
              const evt = parsed.event || parsed.type
              const newContent = parsed.answer || parsed.content || parsed.text || ''

              // 调试日志
              if (evt && evt !== 'message') {
                console.log('SSE事件:', evt, '内容:', newContent)
              }

              if (evt && evt !== 'message' && !newContent) continue
              if (newContent) {
                planContent += newContent
                interviewPlan.value.content = planContent
              } else if (evt && evt === 'message') {
                // 如果是message事件但没有内容，记录日志
                console.log('Message事件无有效内容:', parsed)
              }
            } catch (e) {
              const lower = dataStr.toLowerCase()
              if ((lower.startsWith('{') || lower.startsWith('[')) && lower.includes('"event"')) {
                console.log('跳过SSE事件数据:', dataStr)
                continue
              }
              // 检查是否包含workflow相关关键词
              if (lower.includes('workflow') || lower.includes('conversation_id') || lower.includes('message_id')) {
                console.log('跳过workflow相关数据:', dataStr)
                continue
              }
              if (dataStr && dataStr !== '[DONE]') {
                planContent += dataStr
                interviewPlan.value.content = planContent
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    // 生成完成，更新状态
    if (interviewPlan.value) {
      interviewPlan.value.isGenerating = false
      if (planContent) {
        // 更新本地显示的面试方案内容，保留可能存在的ID
        const existingId = interviewPlan.value.id
        interviewPlan.value = {
          ...interviewPlan.value,
          id: existingId, // 保留现有的ID（如果有的话）
          candidateId: candidate.id,
          candidateName: candidate.name,
          position: candidate.position,
          generatedAt: new Date().toLocaleString(),
          content: planContent,
          isGenerating: false,
          isSaved: false  // 先标记为未保存，自动保存成功后置为已保存
        }
        // 生成即落库，避免方案只存在浏览器里
        await autoSaveInterviewPlan(planContent)
      } else {
        ElMessage.warning('未收到面试方案内容，请重试')
      }
    }
    
  } catch (error) {
    console.error('生成面试方案失败:', error)
    ElMessage.error('生成面试方案失败，请重试')
  } finally {
    generatingPlan.value = false
  }
}

const pad2 = (value) => String(value).padStart(2, '0')

const toIsoWithOffset = (date) => {
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const hours = pad2(Math.floor(Math.abs(offset) / 60))
  const minutes = pad2(Math.abs(offset) % 60)
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}:00${sign}${hours}:${minutes}`
}

const formatDateTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value).replace('T', ' ').slice(0, 16)
  }
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

// 查询候选人当前有效的面试会议，同时刷新按钮状态
const fetchCandidateMeeting = async (candidateId, { sync = false } = {}) => {
  if (!candidateId) {
    candidateMeeting.value = null
    return null
  }
  try {
    const response = await interviewApi.list({
      resume_evaluation_id: candidateId,
      page: 1,
      size: 20,
      sync
    })
    const items = response.items || []
    const meeting = items.find(record =>
      !['cancelled', 'completed'].includes(record.meeting_status)
      && new Date(record.end_time).getTime() > Date.now()
    ) || null
    if (selectedCandidate.value?.id === candidateId) {
      candidateMeeting.value = meeting
    }
    return meeting
  } catch (error) {
    console.warn('查询候选人面试会议失败:', error)
    return null
  }
}

const startInterview = async () => {
  if (!selectedCandidate.value) {
    ElMessage.warning('请先选择候选人')
    return
  }
  if (!interviewPlan.value?.content) {
    ElMessage.warning('请先选择候选人并生成面试方案')
    return
  }

  // 已缓存有效会议：直接展示，避免重复创建
  if (activeMeeting.value) {
    createdMeeting.value = activeMeeting.value
    showMeetingResult.value = true
    return
  }

  // 缓存可能过期（例如刚在别处创建了会议），同步查一次再决定是否新建
  checkingMeeting.value = true
  let meeting = null
  try {
    meeting = await fetchCandidateMeeting(selectedCandidate.value.id, { sync: true })
  } finally {
    checkingMeeting.value = false
  }
  if (meeting) {
    createdMeeting.value = meeting
    showMeetingResult.value = true
    ElMessage.info('该候选人已有面试会议，已展示现有会议信息')
    return
  }

  // 默认开始时间：当前时间后 30 分钟，并取整到下一个半点
  const now = new Date()
  const start = new Date(now.getTime() + 30 * 60 * 1000)
  start.setSeconds(0, 0)
  const remainder = start.getMinutes() % 30
  if (remainder) start.setMinutes(start.getMinutes() + (30 - remainder))
  const end = new Date(start.getTime() + 60 * 60 * 1000)

  createForm.subject = `${selectedCandidate.value.name} - ${selectedCandidate.value.position}面试`
  createForm.timeRange = [start.getTime(), end.getTime()]
  createForm.password = ''
  createForm.autoInWaitingRoom = true
  createForm.autoRecord = true
  showCreateDialog.value = true
}

// 后端 detail 已由 axios 拦截器统一提示，这里只在没有 detail 时兜底，避免同一次错误弹两条
const showApiError = (error, fallback) => {
  if (!error?.response?.data?.detail) {
    ElMessage.error(fallback)
  }
}

const createInterview = async () => {
  if (!selectedCandidate.value) return
  try {
    await createFormRef.value.validate()
  } catch (e) {
    return
  }

  const [start, end] = createForm.timeRange || []
  if (!start || !end) {
    ElMessage.warning('请选择面试开始和结束时间')
    return
  }

  creatingInterview.value = true
  try {
    const data = await interviewApi.start({
      resume_evaluation_id: selectedCandidate.value.id,
      interview_plan_id: interviewPlan.value?.id || undefined,
      interview_plan_content: interviewPlan.value?.content || undefined,
      subject: createForm.subject.trim(),
      start_time: toIsoWithOffset(new Date(start)),
      end_time: toIsoWithOffset(new Date(end)),
      password: createForm.password || undefined,
      auto_in_waiting_room: createForm.autoInWaitingRoom,
      auto_record: createForm.autoRecord
    })
    showCreateDialog.value = false
    createdMeeting.value = data
    candidateMeeting.value = data
    showMeetingResult.value = true
    ElMessage.success('腾讯会议创建成功')
  } catch (error) {
    console.error('创建面试会议失败:', error)
    showApiError(error, '创建会议失败，请检查腾讯会议配置')
  } finally {
    creatingInterview.value = false
  }
}

const openEditMeeting = async (record) => {
  const start = new Date(record.start_time).getTime()
  const end = new Date(record.end_time).getTime()
  editForm.id = record.id
  editForm.subject = record.subject
  editForm.timeRange = [
    Number.isNaN(start) ? Date.now() : start,
    Number.isNaN(end) ? Date.now() + 60 * 60 * 1000 : end
  ]
  editForm.password = record.password || ''
  editForm.autoInWaitingRoom = record.auto_in_waiting_room !== false
  editForm.autoRecord = true
  showMeetingResult.value = false
  showEditDialog.value = true

  // 拉取腾讯会议当前录制设置，覆盖默认值
  try {
    const settings = await interviewApi.getRecordSettings(record.id)
    if (settings?.auto_record != null) {
      editForm.autoRecord = settings.auto_record
    }
  } catch (e) {
    console.warn('读取会议录制设置失败，使用默认值:', e)
  }
}

const saveMeetingEdit = async () => {
  try {
    await editFormRef.value.validate()
  } catch (e) {
    return
  }
  const [start, end] = editForm.timeRange || []
  if (!start || !end) {
    ElMessage.warning('请选择面试开始和结束时间')
    return
  }

  savingMeeting.value = true
  try {
    const updated = await interviewApi.update(editForm.id, {
      subject: editForm.subject.trim(),
      start_time: toIsoWithOffset(new Date(start)),
      end_time: toIsoWithOffset(new Date(end)),
      password: editForm.password || undefined,
      auto_in_waiting_room: editForm.autoInWaitingRoom,
      auto_record: editForm.autoRecord
    })
    showEditDialog.value = false
    if (createdMeeting.value?.id === updated.id) {
      createdMeeting.value = updated
    }
    if (candidateMeeting.value?.id === updated.id) {
      candidateMeeting.value = updated
    }
    ElMessage.success('会议已更新')
    await fetchInterviewRecords()
  } catch (error) {
    console.error('修改会议失败:', error)
    showApiError(error, '修改会议失败')
  } finally {
    savingMeeting.value = false
  }
}

const copyText = async (text) => {
  if (!text) return
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制')
  } catch (error) {
    console.error('复制失败:', error)
    ElMessage.error('复制失败，请手动复制')
  }
}

const copyMeetingInfo = () => {
  const meeting = createdMeeting.value
  if (!meeting) return
  const lines = [
    `会议主题：${meeting.subject}`,
    `开始时间：${formatDateTime(meeting.start_time)}`,
    `结束时间：${formatDateTime(meeting.end_time)}`,
    `会议号：${meeting.meeting_code || '-'}`,
    meeting.password ? `会议密码：${meeting.password}` : '',
    `入会链接：${meeting.join_url}`
  ].filter(Boolean)
  copyText(lines.join('\n'))
}

const viewInterviewRecords = () => {
  showMeetingResult.value = false
  activeTab.value = 'interview-records'
  fetchInterviewRecords()
}

const meetingPhase = (record) => {
  if (!record) return 'scheduled'
  if (record.meeting_status === 'cancelled') return 'cancelled'
  if (record.meeting_status === 'completed') return 'completed'
  // 腾讯会议里已提前开始（同步回来的真实状态）
  if (record.meeting_status === 'ongoing') return 'ongoing'
  const start = new Date(record.start_time).getTime()
  const end = new Date(record.end_time).getTime()
  if (!Number.isNaN(end) && nowMs.value >= end) return 'ended'
  if (!Number.isNaN(start) && nowMs.value >= start) return 'ongoing'
  return 'scheduled'
}

const meetingStatusLabel = (phase) => ({
  scheduled: '已预约',
  ongoing: '进行中',
  ended: '已结束',
  completed: '已完成',
  cancelled: '已取消'
}[phase] || phase || '-')

const meetingTagType = (phase) => ({
  scheduled: 'success',
  ongoing: 'warning',
  ended: 'info',
  completed: 'success',
  cancelled: 'info'
}[phase] || 'info')

const analysisButtonText = (record) => {
  if (analyzingId.value === record.id) return '触发中…'
  if (record.analysis_status === 'analyzing') return '分析中…'
  if (record.analysis_status === 'transcribing') return '转写中…'
  return record.evaluation ? '重新分析' : '开始分析'
}

const analysisDisplayLabel = (record) => {
  if (record.analysis_status === 'not_started') {
    const phase = meetingPhase(record)
    if (phase === 'ongoing') return '面试中'
    if (phase === 'ended' || phase === 'completed') return '待上传结果'
  }
  return analysisStatusLabel(record.analysis_status)
}

const analysisStatusLabel = (status) => ({
  not_started: '未开始',
  transcribing: '转写中',
  transcript_ready: '待分析',
  analyzing: '分析中',
  completed: '已完成',
  failed: '失败'
}[status] || status || '-')

const analysisTagType = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'transcribing' || status === 'analyzing') return 'warning'
  return 'info'
}

const recommendationType = (recommendation) => {
  if (recommendation === '推荐') return 'success'
  if (recommendation === '不推荐') return 'danger'
  return 'warning'
}

const stopRecordPolling = () => {
  if (recordPollingTimer) {
    clearInterval(recordPollingTimer)
    recordPollingTimer = null
  }
}

const startRecordPolling = () => {
  if (recordPollingTimer) return
  recordPollingTimer = setInterval(async () => {
    const activeRecords = interviewRecords.value.filter(
      record => ['transcribing', 'analyzing'].includes(record.analysis_status)
    )
    if (activeRecords.length === 0 || !selectedCandidate.value) {
      stopRecordPolling()
      return
    }
    try {
      const results = await Promise.all(
        activeRecords.map(record => interviewApi.get(record.id).catch(() => null))
      )
      results.forEach(updated => {
        if (!updated) return
        const index = interviewRecords.value.findIndex(item => item.id === updated.id)
        if (index !== -1) interviewRecords.value[index] = updated
      })
      if (!interviewRecords.value.some(
        record => ['transcribing', 'analyzing'].includes(record.analysis_status)
      )) {
        stopRecordPolling()
      }
    } catch (error) {
      console.error('轮询面试进度失败:', error)
    }
  }, 3000)
}

const fetchInterviewRecords = async () => {
  if (!selectedCandidate.value) {
    interviewRecords.value = []
    return
  }
  loadingRecords.value = true
  try {
    const response = await interviewApi.list({
      resume_evaluation_id: selectedCandidate.value.id,
      page: 1,
      size: 50,
      sync: true
    })
    interviewRecords.value = response.items || []
    candidateMeeting.value = interviewRecords.value.find(record =>
      !['cancelled', 'completed'].includes(record.meeting_status)
      && new Date(record.end_time).getTime() > Date.now()
    ) || null
    if (interviewRecords.value.some(
      record => ['transcribing', 'analyzing'].includes(record.analysis_status)
    )) {
      startRecordPolling()
    }
  } catch (error) {
    console.error('获取面试记录失败:', error)
    ElMessage.error('获取面试记录失败')
  } finally {
    loadingRecords.value = false
  }
}

const handleTabChange = (name) => {
  if (name === 'interview-records') {
    fetchInterviewRecords()
  }
}

const handleMediaSelected = async (record, uploadFile) => {
  const raw = uploadFile?.raw
  if (!raw) return
  const maxBytes = 500 * 1024 * 1024
  if (raw.size > maxBytes) {
    ElMessage.error('文件超过 500MB 限制')
    return
  }

  // 先把姓名确认掉再传：转写完成后会自动分析，届时姓名已经定下来了
  uploadForm.recordId = record.id
  uploadForm.file = raw
  uploadForm.filename = raw.name
  uploadForm.candidateName = record.candidate_name || ''
  showUploadDialog.value = true
}

const confirmUpload = async () => {
  const { recordId, file, candidateName } = uploadForm
  if (!recordId || !file) return

  uploadingId.value = recordId
  showUploadDialog.value = false
  try {
    await interviewApi.uploadMedia(recordId, file, candidateName.trim())
    ElMessage.success('上传成功，正在转写')
    uploadForm.file = null
    await fetchInterviewRecords()
    startRecordPolling()
  } catch (error) {
    console.error('上传面试材料失败:', error)
    showApiError(error, '上传失败')
  } finally {
    uploadingId.value = null
  }
}

const openCandidateDialog = (record) => {
  candidateForm.recordId = record.id
  candidateForm.candidateName = record.candidate_name || ''
  candidateForm.hasEvaluation = !!record.evaluation
  showCandidateDialog.value = true
}

const saveCandidateName = async () => {
  if (!candidateForm.recordId) return
  const name = candidateForm.candidateName.trim()
  const previous = interviewRecords.value.find((item) => item.id === candidateForm.recordId)
  if (name === (previous?.candidate_name || '')) {
    showCandidateDialog.value = false
    return
  }

  savingCandidate.value = true
  try {
    await interviewApi.updateCandidateName(candidateForm.recordId, name)
    showCandidateDialog.value = false
    await fetchInterviewRecords()
    if (candidateForm.hasEvaluation) {
      ElMessage.warning('姓名已更新，原评价已作废，请重新分析')
    } else {
      ElMessage.success('候选人姓名已更新')
    }
  } catch (error) {
    console.error('更新候选人姓名失败:', error)
    showApiError(error, '更新姓名失败')
  } finally {
    savingCandidate.value = false
  }
}

const pullTencentTranscript = async (record) => {
  pullingId.value = record.id
  try {
    await interviewApi.pullTencent(record.id)
    ElMessage.success('已开始拉取腾讯会议转写')
    await fetchInterviewRecords()
    startRecordPolling()
  } catch (error) {
    console.error('拉取腾讯会议转写失败:', error)
    showApiError(error, '拉取转写失败')
  } finally {
    pullingId.value = null
  }
}

const syncMeetingStatus = async (record) => {
  syncingId.value = record.id
  try {
    await interviewApi.syncMeeting(record.id)
    ElMessage.success('已从腾讯会议同步会议状态')
    await fetchInterviewRecords()
  } catch (error) {
    console.error('同步会议状态失败:', error)
    showApiError(error, '同步失败')
  } finally {
    syncingId.value = null
  }
}

const reanalyze = async (record) => {
  analyzingId.value = record.id
  try {
    await interviewApi.analyze(record.id)
    ElMessage.success('已开始 AI 分析')
    await fetchInterviewRecords()
    startRecordPolling()
  } catch (error) {
    console.error('触发面试分析失败:', error)
    showApiError(error, '分析失败')
  } finally {
    analyzingId.value = null
  }
}

// ---------- 人工修订评分 ----------
const showScoreDialog = ref(false)
const savingScores = ref(false)
const scoreEditingRecord = ref(null)
const scoreForm = reactive({ dimensions: [], recommendation: '待定', note: '' })

const lastOverrideNote = (record) => {
  const history = record.evaluation?.manual_override?.history || []
  return history.length ? history[history.length - 1].note : ''
}

const openScoreEditor = (record) => {
  const evaluation = record.evaluation
  if (!evaluation?.dimensions?.length) {
    ElMessage.warning('这条记录还没有可修订的评分维度')
    return
  }
  scoreEditingRecord.value = record
  scoreForm.dimensions = evaluation.dimensions.map((dim) => {
    // 已经人工改过的维度，对比基准仍取 AI 原分，避免反复修订后基准越飘越远
    const baseline = dim.manual && dim.ai_score != null ? dim.ai_score : dim.score
    return {
      name: dim.name,
      ai_score: baseline,
      original: baseline,
      score: dim.score
    }
  })
  scoreForm.recommendation = evaluation.recommendation || '待定'
  scoreForm.note = ''
  showScoreDialog.value = true
}

const saveScoreOverride = async () => {
  const record = scoreEditingRecord.value
  if (!record) return
  if (!scoreForm.note.trim()) {
    ElMessage.warning('请填写修订原因，方便事后核对')
    return
  }
  const changes = scoreForm.dimensions.filter((dim) => dim.score !== dim.original)
  const conclusionChanged = scoreForm.recommendation !== (record.evaluation.recommendation || '待定')
  if (!changes.length && !conclusionChanged) {
    ElMessage.warning('分数和推荐结论都没有改动')
    return
  }

  savingScores.value = true
  try {
    const evaluation = await interviewApi.updateEvaluation(record.id, {
      dimensions: changes.map((dim) => ({ name: dim.name, score: dim.score })),
      recommendation: scoreForm.recommendation,
      note: scoreForm.note.trim()
    })
    record.evaluation = evaluation
    record.total_score = evaluation.total_score
    showScoreDialog.value = false
    ElMessage.success(`已保存修订，总分 ${evaluation.total_score}`)
  } catch (error) {
    console.error('保存评分修订失败:', error)
    showApiError(error, '保存修订失败')
  } finally {
    savingScores.value = false
  }
}

const cancelInterviewRecord = async (record) => {
  try {
    await ElMessageBox.confirm(
      `确定取消「${record.subject}」这场面试会议吗？`,
      '取消会议',
      { confirmButtonText: '确定取消', cancelButtonText: '返回', type: 'warning' }
    )
    await interviewApi.cancel(record.id)
    if (candidateMeeting.value?.id === record.id) {
      candidateMeeting.value = null
    }
    ElMessage.success('会议已取消')
    await fetchInterviewRecords()
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      console.error('取消会议失败:', error)
      showApiError(error, '取消会议失败')
    }
  }
}

const exportPlan = (format = 'txt') => {
  if (!interviewPlan.value) {
    ElMessage.warning('暂无面试方案可导出')
    return
  }

  const plan = interviewPlan.value
  const content = `面试方案 - ${plan.candidateName}
职位：${plan.position}
生成时间：${plan.generatedAt || new Date().toLocaleString()}

${plan.content}`

  // 创建文件名
  const fileName = `面试方案_${plan.candidateName}_${new Date().toISOString().slice(0, 10)}.${format}`

  // 根据格式导出
  switch (format) {
    case 'txt':
      exportAsText(content, fileName)
      break
    case 'md':
      exportAsMarkdown(plan, fileName)
      break
    default:
      exportAsText(content, fileName)
  }

  ElMessage.success(`面试方案已导出为 ${format.toUpperCase()} 格式`)
}

// 导出为文本文件
const exportAsText = (content, fileName) => {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = fileName
  link.click()
  URL.revokeObjectURL(link.href)
}

// 导出为Markdown文件
const exportAsMarkdown = (plan, fileName) => {
  const markdownContent = `# 面试方案

## 候选人信息
- **姓名**：${plan.candidateName}
- **应聘职位**：${plan.position}
- **生成时间**：${plan.generatedAt || new Date().toLocaleString()}

## 面试方案内容
${plan.content}`

  const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = fileName
  link.click()
  URL.revokeObjectURL(link.href)
}

const regeneratePlan = () => {
  if (!selectedCandidate.value) {
    ElMessage.warning('请先选择候选人')
    return
  }
  generateInterviewPlan(selectedCandidate.value)
}

// 编辑面试方案相关方法
const toggleEditPlan = () => {
  console.log('toggleEditPlan 被调用')
  console.log('当前 interviewPlan:', interviewPlan.value)
  console.log('interviewPlan.value?.id:', interviewPlan.value?.id)
  
  if (!interviewPlan.value?.content) {
    ElMessage.warning('暂无面试方案内容可编辑')
    return
  }
  
  isEditingPlan.value = true
  originalPlanContent.value = interviewPlan.value.content
  editPlanContent.value = interviewPlan.value.content
  
  console.log('编辑模式开启后，interviewPlan.value?.id:', interviewPlan.value?.id)
}

const cancelEditPlan = () => {
  isEditingPlan.value = false
  editPlanContent.value = ''
  originalPlanContent.value = ''
}



// 保存面试方案的公共实现：有 id 走更新，无 id 走新建
const persistInterviewPlan = async (contentToSave) => {
  const candidate = selectedCandidate.value
  if (!candidate) throw new Error('未选择候选人')

  let planId = interviewPlan.value?.id || null
  // 本地没有 id 时先查一次，避免为同一候选人重复创建方案记录
  if (!planId) {
    try {
      const existing = await hrWorkflowsApi.getInterviewPlanList({
        resume_evaluation_id: candidate.id,
        limit: 1
      })
      planId = existing?.items?.[0]?.id || null
    } catch (error) {
      console.warn('查询已有面试方案失败，将按新建处理:', error)
    }
  }

  const planName = interviewPlan.value?.candidateName || candidate.name || '未知候选人'
  const planPosition = interviewPlan.value?.position || candidate.position || '未填写'

  const response = planId
    ? await hrWorkflowsApi.updateInterviewPlan(planId, {
        content: contentToSave,
        candidate_name: planName,
        candidate_position: planPosition
      })
    : await hrWorkflowsApi.saveGeneratedInterviewPlan({
        resume_evaluation_id: candidate.id,
        candidate_name: planName,
        candidate_position: planPosition,
        content: contentToSave
      })

  if (!response) throw new Error('保存接口未返回数据')

  interviewPlan.value = {
    ...interviewPlan.value,
    id: response.id || planId,
    candidateId: candidate.id,
    candidateName: planName,
    position: planPosition,
    content: response.content || contentToSave,
    createdAt: response.created_at,
    updatedAt: response.updated_at,
    generatedAt: interviewPlan.value?.generatedAt || new Date().toLocaleString(),
    isGenerating: false,
    isSaved: true,
    savedAt: new Date().toLocaleString()
  }
  return { response, created: !planId }
}

// 生成完成后自动落库；失败不阻断流程，回落到手动保存
const autoSaveInterviewPlan = async (content) => {
  if (!content || !content.trim()) return false
  if (content.trim().length < 50) {
    console.warn('面试方案内容过短，跳过自动保存')
    return false
  }
  const looksLikeStreamJunk =
    content.includes('"conversation_id"') ||
    content.includes('"message_id"') ||
    content.includes('"workflow_started"')
  if (looksLikeStreamJunk) {
    console.warn('面试方案内容混入流式事件数据，跳过自动保存')
    ElMessage.warning('方案内容异常，已跳过自动保存，请检查后手动保存')
    return false
  }

  autoSavingPlan.value = true
  try {
    const { created } = await persistInterviewPlan(content)
    ElMessage.success(created ? '面试方案已生成并自动保存' : '面试方案已生成并更新保存')
    return true
  } catch (error) {
    console.error('自动保存面试方案失败:', error)
    if (interviewPlan.value) {
      interviewPlan.value = { ...interviewPlan.value, isSaved: false }
    }
    ElMessage.warning('方案已生成，但自动保存失败，请点击「保存方案」手动保存')
    return false
  } finally {
    autoSavingPlan.value = false
  }
}

// 统一的保存面试方案方法（手动保存 / 编辑后保存）
const saveInterviewPlan = async () => {
  // 获取要保存的内容
  const contentToSave = isEditingPlan.value ? editPlanContent.value : interviewPlan.value?.content

  if (!contentToSave?.trim()) {
    ElMessage.warning('面试方案内容不能为空')
    return
  }

  if (!selectedCandidate.value) {
    ElMessage.warning('请先选择候选人')
    return
  }

  try {
    savingPlan.value = true
    const { created } = await persistInterviewPlan(contentToSave)

    // 如果是编辑模式，退出编辑
    if (isEditingPlan.value) {
      isEditingPlan.value = false
      editPlanContent.value = ''
      originalPlanContent.value = ''
    }

    // 强制切换到面试方案标签页以显示更新的内容
    activeTab.value = 'interview-plan'
    await nextTick()

    ElMessage.success(created ? '面试方案保存成功' : '面试方案更新成功')
  } catch (error) {
    console.error('保存面试方案失败:', error)
    ElMessage.error('保存面试方案失败，请重试')
  } finally {
    savingPlan.value = false
  }
}

// 保持向后兼容的方法
const saveGeneratedPlan = saveInterviewPlan

// 筛选相关方法
const handleFilterChange = () => {
  // 筛选变化时的处理逻辑
  if (selectedCandidate.value && !filteredCandidates.value.find(c => c.id === selectedCandidate.value.id)) {
    // 如果当前选中的候选人被筛选掉了，清除选择
    selectedCandidate.value = null
    interviewPlan.value = null
    activeTab.value = 'resume'
  }
}

const clearFilters = () => {
  filters.name = ''
  filters.position = ''
  ElMessage.success('筛选条件已重置')
}

// 组件挂载时获取数据
onMounted(() => {
  fetchCandidates()
  clockTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 30000)
})

onUnmounted(() => {
  stopRecordPolling()
  if (clockTimer) {
    clearInterval(clockTimer)
    clockTimer = null
  }
})
</script>

<style lang="scss" scoped>
.smart-interview {
  height: 100%;
  overflow-y: auto;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  min-height: 100vh;
}

.page-container {
  max-width: 95%;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  margin-bottom: 24px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  padding: 24px;
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  
  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 24px;
    
    .header-left {
      flex: 1;
    }
    
    .page-title {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 28px;
      font-weight: 700;
      background: linear-gradient(135deg, #667eea, #764ba2);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin: 0 0 8px 0;
      
      .el-icon {
        font-size: 32px;
        color: #667eea;
      }
    }
    
    .page-subtitle {
      color: #64748b;
      margin: 0;
      font-size: 16px;
    }
    
    .filter-section {
      flex-shrink: 0;
      
      .filter-row {
        display: flex;
        align-items: flex-end;
        gap: 16px;
        flex-wrap: wrap;
      }
      
      .filter-item {
        display: flex;
        flex-direction: column;
        gap: 6px;
        
        .filter-label {
          font-size: 14px;
          font-weight: 500;
          color: #374151;
          margin: 0;
        }
      }
      
      .filter-actions {
        display: flex;
        align-items: center;
        gap: 12px;
        
        .el-button {
          background: linear-gradient(135deg, #f3f4f6, #e5e7eb);
          border: 1px solid #d1d5db;
          color: #374151;
          border-radius: 8px;
          font-weight: 500;
          transition: all 0.3s ease;
          
          &:hover {
            background: linear-gradient(135deg, #e5e7eb, #d1d5db);
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          }
        }
        
        .el-tag {
          font-weight: 500;
        }
      }
    }
  }
  
  .header-actions {
    .el-button {
      background: linear-gradient(135deg, #667eea, #764ba2);
      border: none;
      color: white;
      padding: 12px 24px;
      border-radius: 12px;
      font-weight: 600;
      transition: all 0.3s ease;
      
      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
      }
    }
  }
}

.main-content {
  display: flex;
  gap: 20px;
  height: calc(100vh - 200px);
}

.left-panel {
  width: 400px;
  flex-shrink: 0;
  max-width: 30%;
}

.right-panel {
  flex: 1;
  min-width: 0;
}

.candidate-list-card {
  height: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  
  :deep(.el-card__header) {
    background: linear-gradient(135deg, #f8fafc, #e2e8f0);
    border-bottom: 1px solid rgba(226, 232, 240, 0.5);
    border-radius: 16px 16px 0 0;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    color: #1e293b;
  }
}

.candidate-list {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}

.candidate-item {
  padding: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: #fff;
  
  &:hover {
    border-color: #409eff;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.1);
  }
  
  &.active {
    border-color: #409eff;
    background: #f0f9ff;
    box-shadow: 0 2px 8px rgba(64, 158, 255, 0.2);
  }
}

.candidate-info {
  margin-bottom: 12px;
}

.candidate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.candidate-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.candidate-position {
  margin: 0 0 8px 0;
  color: #606266;
  font-size: 14px;
}

.candidate-details {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-item {
  font-size: 12px;
  color: #909399;
  background: #f5f7fa;
  padding: 2px 8px;
  border-radius: 4px;
}

.score-items {
  margin-bottom: 12px;
}

.score-row {
  display: flex;
  gap: 16px;
  margin-bottom: 8px;
  align-items: center;
  
  &:last-child {
    margin-bottom: 0;
  }
}

.score-item {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  
  .score-label {
    display: block;
    font-size: 12px;
    color: #606266;
    font-weight: 500;
    min-width: 80px;
    text-align: right;
  }
  
  .score-display {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    
    .actual-score {
      font-size: 12px;
      font-weight: 600;
      color: #303133;
      min-width: 50px;
    }
    
    .el-progress {
      flex: 1;
      max-width: 120px;
    }
  }
}

.candidate-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.empty-candidates {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  
  :deep(.el-empty) {
    .el-empty__description {
      color: #64748b;
      font-size: 14px;
    }
    
    .el-button {
      background: linear-gradient(135deg, #667eea, #764ba2);
      border: none;
      color: white;
      border-radius: 8px;
      font-weight: 500;
      
      &:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.3);
      }
    }
  }
}

.content-card {
  height: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  
  :deep(.el-card__body) {
    height: calc(100% - 60px);
    padding: 0;
  }
}

.content-tabs {
  height: 100%;
  
  :deep(.el-tabs__header) {
    margin: 0;
    padding: 0 20px;
    background: linear-gradient(135deg, #f8fafc, #e2e8f0);
    border-radius: 16px 16px 0 0;
  }
  
  :deep(.el-tabs__content) {
    height: calc(100% - 60px);
    padding: 20px;
  }
  
  :deep(.el-tab-pane) {
    height: 100%;
  }
}

.resume-preview {
  height: 100%;
  overflow-y: auto;
  
  .empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
  }
  
  .resume-content {
    .resume-section {
      margin-bottom: 24px;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #1e293b;
        margin: 0 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #e2e8f0;
      }
    }
    
    .personal-info {
      .info-row {
        display: flex;
        gap: 24px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .info-item {
          flex: 1;
          
          label {
            font-weight: 600;
            color: #64748b;
            margin-right: 8px;
          }
          
          span {
            color: #1e293b;
          }
        }
      }
    }
    
    .experience-list {
      .experience-item {
        padding: 16px;
        background: #f8fafc;
        border-radius: 8px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .exp-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          
          h4 {
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
          }
          
          .duration {
            font-size: 14px;
            color: #64748b;
            background: #e2e8f0;
            padding: 4px 8px;
            border-radius: 4px;
          }
        }
        
        .company {
          margin: 0 0 8px 0;
          font-weight: 500;
          color: #475569;
        }
        
        .description {
          margin: 0;
          color: #64748b;
          line-height: 1.5;
        }
      }
    }
    
    .education-list {
      .education-item {
        padding: 16px;
        background: #f8fafc;
        border-radius: 8px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .edu-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          
          h4 {
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
          }
          
          .duration {
            font-size: 14px;
            color: #64748b;
            background: #e2e8f0;
            padding: 4px 8px;
            border-radius: 4px;
          }
        }
        
        .major {
          margin: 0;
          color: #475569;
          font-weight: 500;
        }
      }
    }
    
    .skills-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      
      .skill-tag {
        margin: 0;
      }
    }
  }
}

.interview-plan-preview {
  height: 100%;
  overflow-y: auto;
  
  .empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
  }
  
  .interview-plan-content {
    .plan-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 24px;
      padding: 20px;
      background: linear-gradient(135deg, #f8fafc, #e2e8f0);
      border-radius: 8px;
      
      .header-info {
        h2 {
          margin: 0 0 8px 0;
          font-size: 20px;
          font-weight: 600;
          color: #1e293b;
        }
        
        .position {
          margin: 0 0 4px 0;
          color: #475569;
          font-weight: 500;
        }
        
        .generated-time {
          margin: 0;
          font-size: 14px;
          color: #64748b;
        }
      }
    }
    
    // Markdown内容样式优化
    .markdown-content {
      line-height: 1.6;
      color: #374151;
      
      h1, h2, h3, h4, h5, h6 {
        color: #1e293b;
        font-weight: 600;
        margin: 24px 0 16px 0;
        
        &:first-child {
          margin-top: 0;
        }
      }
      
      h1 {
        font-size: 24px;
        border-bottom: 2px solid #e2e8f0;
        padding-bottom: 8px;
      }
      
      h2 {
        font-size: 20px;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 6px;
      }
      
      h3 {
        font-size: 18px;
        color: #667eea;
      }
      
      h4 {
        font-size: 16px;
      }
      
      p {
        margin: 12px 0;
        line-height: 1.7;
      }
      
      ul, ol {
        margin: 16px 0;
        padding-left: 24px;
        
        li {
          margin: 8px 0;
          line-height: 1.6;
          
          &::marker {
            color: #667eea;
          }
        }
      }
      
      ul {
        li {
          position: relative;
          
          &::before {
            content: '•';
            color: #667eea;
            font-weight: bold;
            position: absolute;
            left: -16px;
          }
        }
      }
      
      blockquote {
        margin: 16px 0;
        padding: 16px 20px;
        background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
        border-left: 4px solid #667eea;
        border-radius: 0 8px 8px 0;
        
        p {
          margin: 0;
          color: #1e40af;
          font-style: italic;
        }
      }
      
      code {
        background: #f1f5f9;
        color: #e11d48;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 0.9em;
      }
      
      pre {
        background: #1e293b;
        color: #e2e8f0;
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 16px 0;
        
        code {
          background: none;
          color: inherit;
          padding: 0;
        }
      }
      
      table {
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0;
        background: white;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        
        th, td {
          padding: 12px 16px;
          text-align: left;
          border-bottom: 1px solid #e2e8f0;
        }
        
        th {
          background: linear-gradient(135deg, #f8fafc, #e2e8f0);
          font-weight: 600;
          color: #1e293b;
        }
        
        tr:hover {
          background: #f8fafc;
        }
      }
      
      strong {
        color: #1e293b;
        font-weight: 600;
      }
      
      em {
        color: #667eea;
        font-style: italic;
      }
      
      hr {
        border: none;
        height: 2px;
        background: linear-gradient(135deg, #e2e8f0, #cbd5e1);
        margin: 24px 0;
        border-radius: 1px;
      }
    }
    
    .plan-section {
      margin-bottom: 24px;
      
      &:last-child {
        margin-bottom: 0;
      }
      
      .section-title {
        font-size: 18px;
        font-weight: 600;
        color: #1e293b;
        margin: 0 0 16px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #e2e8f0;
      }
    }
    
    .overview-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      
      .overview-item {
        &.full-width {
          grid-column: 1 / -1;
        }
        
        label {
          font-weight: 600;
          color: #64748b;
          margin-right: 8px;
        }
        
        span {
          color: #1e293b;
        }
        
        .focus-areas {
          margin-top: 8px;
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          
          .area-tag {
            margin: 0;
          }
        }
      }
    }
    
    .sections-list {
      .section-item {
        padding: 16px;
        background: #f8fafc;
        border-radius: 8px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
          
          h4 {
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
          }
          
          .duration {
            font-size: 14px;
            color: #64748b;
            background: #e2e8f0;
            padding: 4px 8px;
            border-radius: 4px;
          }
        }
        
        .questions-list {
          .question-item {
            display: flex;
            gap: 8px;
            margin-bottom: 8px;
            
            &:last-child {
              margin-bottom: 0;
            }
            
            .question-number {
              font-weight: 600;
              color: #667eea;
              flex-shrink: 0;
            }
            
            .question-text {
              color: #475569;
              line-height: 1.5;
            }
          }
        }
      }
    }
    
    .criteria-list {
      .criteria-item {
        padding: 16px;
        background: #f8fafc;
        border-radius: 8px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .criteria-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;
          
          h4 {
            margin: 0;
            font-size: 16px;
            font-weight: 600;
            color: #1e293b;
          }
        }
        
        .criteria-description {
          margin: 0;
          color: #64748b;
          line-height: 1.5;
        }
      }
    }
    
    .tips-list {
      .tip-item {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        margin-bottom: 12px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .tip-icon {
          color: #667eea;
          margin-top: 2px;
          flex-shrink: 0;
        }
        
        span {
          color: #475569;
          line-height: 1.5;
        }
      }
    }
    
    .plan-actions {
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid #e2e8f0;
      display: flex;
      gap: 16px;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      
      .action-group {
        display: flex;
        gap: 12px;
        align-items: center;
      }
      
      .el-button {
        border-radius: 8px;
        font-weight: 500;
        
        &.el-button--primary {
          background: linear-gradient(135deg, #667eea, #764ba2);
          border: none;
          color: #fff;
        }
        
        // 会议态按钮（success/warning）本身带 plain，实心底色需配白字，否则默认同色系浅色文字会看不清
        &.el-button--success {
          background: linear-gradient(135deg, #10b981, #059669);
          border: none;
          color: #fff;
          font-weight: 600;
        }
        
        &.el-button--warning {
          background: linear-gradient(135deg, #f59e0b, #d97706);
          border: none;
          color: #fff;
          font-weight: 600;
        }
        
        &:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      }
    }
    
    .edit-container {
      margin-top: 16px;
      
      .edit-textarea {
        :deep(.el-textarea__inner) {
          border-radius: 8px;
          border: 2px solid #e2e8f0;
          font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
          font-size: 14px;
          line-height: 1.6;
          padding: 16px;
          transition: all 0.3s ease;
          
          &:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
          }
        }
      }
    }
  }
}

.interview-items {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.interview-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(248, 250, 252, 0.9));
  border: 1px solid rgba(226, 232, 240, 0.5);
  border-radius: 12px;
  transition: all 0.3s ease;
  
  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 40px rgba(102, 126, 234, 0.15);
    border-color: rgba(102, 126, 234, 0.3);
  }
  
  .interview-info {
    flex: 1;
    
    .candidate-info {
      margin-bottom: 12px;
      
      h3 {
        font-size: 18px;
        font-weight: 600;
        background: linear-gradient(135deg, #1e293b, #475569);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0 0 4px 0;
      }
      
      p {
        color: #64748b;
        margin: 0;
        font-weight: 500;
      }
    }
    
    .interview-details {
      display: flex;
      gap: 24px;
      
      .detail-item {
        display: flex;
        align-items: center;
        gap: 6px;
        color: #64748b;
        font-size: 14px;
        font-weight: 500;
        
        .el-icon {
          font-size: 16px;
          color: #667eea;
        }
      }
    }
  }
  
  .interview-actions {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 12px;
    
    .status-tag {
      margin: 0;
      font-weight: 600;
      border-radius: 8px;
      
      &.el-tag--warning {
        background: linear-gradient(135deg, #fbbf24, #f59e0b);
        color: white;
        border: none;
      }
      
      &.el-tag--success {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        border: none;
      }
    }
    
    .action-buttons {
      display: flex;
      gap: 8px;
      
      .el-button {
        border-radius: 8px;
        font-weight: 500;
        
        &.el-button--primary {
          background: linear-gradient(135deg, #667eea, #764ba2);
          border: none;
          
          &:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
          }
        }
        
        &:not(.el-button--primary) {
          background: rgba(255, 255, 255, 0.8);
          border: 1px solid rgba(226, 232, 240, 0.8);
          color: #64748b;
          
          &:hover {
            background: rgba(248, 250, 252, 0.9);
            border-color: rgba(102, 126, 234, 0.3);
            color: #667eea;
          }
        }
      }
    }
  }
}

// 对话框样式优化
:deep(.el-dialog) {
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  
  .el-dialog__header {
    background: linear-gradient(135deg, #f8fafc, #e2e8f0);
    border-radius: 16px 16px 0 0;
    padding: 20px 24px;
    
    .el-dialog__title {
      font-weight: 600;
      color: #1e293b;
    }
  }
  
  .el-dialog__body {
    padding: 24px;
  }
  
  .el-dialog__footer {
    padding: 20px 24px;
    background: rgba(248, 250, 252, 0.5);
    border-radius: 0 0 16px 16px;
    
    .el-button {
      border-radius: 8px;
      font-weight: 500;
      
      &.el-button--primary {
        background: linear-gradient(135deg, #667eea, #764ba2);
        border: none;
      }
    }
  }
}

// 表单样式优化
:deep(.el-form) {
  .el-form-item__label {
    color: #374151;
    font-weight: 600;
  }
  
  .el-input__wrapper {
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    
    &:hover {
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    }
  }
  
  .el-radio {
    .el-radio__label {
      color: #374151;
      font-weight: 500;
    }
  }
  
  .el-textarea__inner {
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    
    &:hover {
      box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);
    }
  }
}

// 响应式设计
@media (max-width: 1200px) {
  .left-panel {
    width: 350px;
    max-width: 35%;
  }
}

@media (max-width: 768px) {
  .smart-interview {
    padding: 12px;
  }
  
  .page-header {
    padding: 20px;
    
    .header-content {
      flex-direction: column;
      gap: 20px;
      
      .filter-section {
        .filter-row {
          flex-direction: column;
          gap: 12px;
          align-items: stretch;
        }
        
        .filter-item {
          .el-input,
          .el-select {
            width: 100% !important;
          }
        }
        
        .filter-actions {
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 8px;
          
          .el-button {
            flex: 1;
            min-width: 120px;
          }
        }
      }
    }
    
    .header-actions {
      width: 100%;
      display: flex;
      justify-content: center;
    }
  }
  
  .main-content {
    flex-direction: column;
    height: auto;
    gap: 16px;
  }
  
  .left-panel {
    width: 100%;
  }
  
  .candidate-list {
    max-height: 400px;
  }
  
  .candidate-item {
    .candidate-details {
      flex-direction: column;
      gap: 8px;
    }
    
    .score-row {
      flex-direction: column;
      gap: 8px;
      align-items: stretch;
      
      .score-item {
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
        
        .score-label {
          text-align: left;
          min-width: auto;
        }
      }
    }
    
    .candidate-actions {
      flex-direction: column;
      gap: 8px;
      
      .el-button {
        width: 100%;
      }
    }
  }
  
  .overview-grid {
    grid-template-columns: 1fr !important;
  }
  
  .plan-actions {
    flex-direction: column;
    
    .el-button {
      width: 100%;
    }
  }
}

// 简历预览样式
.resume-detail-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  
  .detail-header {
    background: rgba(255, 255, 255, 0.95);
    padding: 24px;
    border-radius: 16px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    
    .candidate-profile {
      display: flex;
      align-items: center;
      gap: 16px;
      
      .profile-info {
        h3 {
          margin: 0 0 4px 0;
          color: #303133;
          font-size: 20px;
        }
        
        .current-position {
          color: #606266;
          margin: 0 0 8px 0;
          font-size: 14px;
        }
        
        .profile-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          color: #909399;
          
          .meta-divider {
            color: #dcdfe6;
          }
        }
      }
    }
    
    .score-section {
      text-align: center;

      .score-display {
        margin-bottom: 8px;
        
        .score-text {
          font-size: 14px;
          font-weight: 600;
        }
      }
      
      .score-label {
        margin: 0;
        font-size: 12px;
        color: #909399;
      }
    }
  }
  
  .detail-main {
    flex: 1;
    background: rgba(255, 255, 255, 0.95);
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    min-height: 0;
    padding: 20px;
    
    .two-column-layout {
      display: flex;
      gap: 20px;
      height: 100%;
      
      .left-column,
      .right-column {
        flex: 1;
        display: flex;
        flex-direction: column;
        background: rgba(255, 255, 255, 0.8);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        overflow: hidden;
      }
      
      .column-header {
        background: rgba(102, 126, 234, 0.1);
        padding: 16px 20px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        
        .column-title {
          margin: 0;
          font-size: 16px;
          font-weight: 600;
          color: #667eea;
          display: flex;
          align-items: center;
          gap: 8px;
          
          .el-icon {
            font-size: 18px;
          }
        }
      }
      
      .column-content {
        flex: 1;
        padding: 20px;
        overflow-y: auto;
        
        &::-webkit-scrollbar {
          width: 6px;
        }
        
        &::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 3px;
        }
        
        &::-webkit-scrollbar-thumb {
          background: rgba(102, 126, 234, 0.3);
          border-radius: 3px;
          
          &:hover {
            background: rgba(102, 126, 234, 0.5);
          }
        }
      }
    }
  }
}

.resume-content-section {
  .content-display {
    line-height: 1.6;
    color: #303133;
    
    :deep(h1), :deep(h2), :deep(h3), :deep(h4), :deep(h5), :deep(h6) {
      color: #303133;
      margin-top: 24px;
      margin-bottom: 12px;
    }
    
    :deep(p) {
      margin-bottom: 12px;
    }
    
    :deep(ul), :deep(ol) {
      padding-left: 20px;
      margin-bottom: 12px;
    }
  }
}

.evaluation-section {
  .evaluation-content {
    .evaluation-item {
      background: #f8f9fa;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
      
      .metric-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 12px;
        
        .metric-name {
          margin: 0;
          color: #303133;
          font-size: 16px;
        }
      }
      
      .metric-reason {
        p {
          margin: 0;
          color: #606266;
          line-height: 1.6;
        }
      }
    }
  }
  
  .no-evaluation {
    padding: 40px 20px;
    text-align: center;
  }
}

// 面试记录
.interview-records {
  height: 100%;
  overflow-y: auto;
  padding: 4px 4px 4px 0;

  .records-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;

    .records-title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }
  }

  .record-card {
    border: 1px solid #ebeef5;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
    background: #fff;

    .record-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;

      h4 {
        margin: 0 0 6px;
        color: #303133;
      }

      .record-time {
        margin: 0;
        color: #909399;
        font-size: 13px;
      }

      .record-candidate {
        display: flex;
        align-items: center;
        gap: 4px;
        margin: 6px 0 0;
        color: #606266;
        font-size: 13px;
      }

      .record-tags {
        display: flex;
        gap: 8px;
        flex-shrink: 0;
      }
    }

    .record-meeting {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
      color: #606266;
      font-size: 13px;
      flex-wrap: wrap;
    }

    .record-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 14px;
    }

    .record-error {
      margin-top: 12px;
    }

    .record-progress {
      margin-top: 12px;
    }
  }

  .evaluation-card {
    margin-top: 16px;
    border-radius: 8px;
    background: #f8f9fa;
    padding: 16px;

    .evaluation-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;

      .evaluation-score {
        font-size: 28px;
        font-weight: 700;
        color: #409eff;

        small {
          font-size: 13px;
          font-weight: 400;
          margin-left: 2px;
          color: #909399;
        }
      }

      .evaluation-actions {
        display: flex;
        align-items: center;
        gap: 12px;
      }
    }

    .evaluation-manual {
      margin: -4px 0 12px;
      padding: 8px 12px;
      border-radius: 6px;
      background: #fdf6ec;
      border-left: 3px solid #e6a23c;
      font-size: 13px;
      color: #b88230;
      line-height: 1.6;

      // 修订原因可填 500 字，这里单行截断，完整内容看悬停提示
      .manual-note {
        display: inline-block;
        max-width: min(420px, 100%);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        vertical-align: bottom;
      }
    }

    .manual-tag {
      margin-left: 6px;
    }

    .evaluation-table {
      margin-bottom: 12px;
      background: #fff;
    }

    .evaluation-insufficient {
      margin-top: 12px;
      padding: 10px 12px;
      border-radius: 6px;
      background: #fdf6ec;
      border-left: 3px solid #e6a23c;

      strong {
        display: block;
        font-size: 13px;
        color: #b88230;
        margin-bottom: 6px;
      }

      ul {
        margin: 0;
        padding-left: 18px;

        li {
          font-size: 13px;
          color: #606266;
          line-height: 1.7;
        }
      }
    }

    .evaluation-summary {
      color: #303133;
      line-height: 1.7;
      margin: 0 0 12px;
    }

    .evaluation-lists {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;

      strong {
        display: block;
        margin-bottom: 6px;
        color: #303133;
      }

      ul {
        margin: 0;
        padding-left: 18px;
        color: #606266;
        line-height: 1.6;
      }
    }
  }

  .transcript-preview {
    margin-top: 16px;
    padding: 12px;
    background: #f8f9fa;
    border-radius: 8px;

    .transcript-title {
      margin: 0 0 8px;
      font-weight: 600;
      color: #303133;
    }

    .transcript-text {
      margin: 0;
      color: #606266;
      line-height: 1.6;
      white-space: pre-wrap;
    }
  }
}

.form-hint {
  margin-left: 10px;
  color: #909399;
  font-size: 12px;
}

.score-alert {
  margin-bottom: 14px;
}

.score-table {
  margin-bottom: 18px;
}

.score-unchanged {
  color: #c0c4cc;
  font-size: 12px;
}

.score-form {
  :deep(.el-form-item:last-child) {
    margin-bottom: 0;
  }
}

.upload-alert {
  margin-bottom: 14px;
}

.upload-form {
  .upload-filename {
    color: #303133;
    word-break: break-all;
  }
}

.candidate-form {
  .candidate-hint {
    display: block;
    margin-left: 0;
    line-height: 1.6;
  }

  :deep(.el-alert) {
    margin-top: 4px;
  }
}

.meeting-result {
  .result-subject {
    margin: 0 0 14px;
    font-size: 16px;
    font-weight: 600;
    color: #303133;
  }

  .join-url {
    word-break: break-all;
    color: #409eff;
  }

  .result-actions {
    display: flex;
    gap: 12px;
    margin-top: 18px;
  }
}
</style>
