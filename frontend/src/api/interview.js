import api, { request } from '@/api/index'

export const interviewApi = {
  // 创建腾讯会议并发起面试
  start(data) {
    return request.post('/interviews/start', data)
  },

  // 面试记录列表
  list(params = {}) {
    return request.get('/interviews/', { params })
  },

  get(interviewId) {
    return request.get(`/interviews/${interviewId}`)
  },

  cancel(interviewId) {
    return request.post(`/interviews/${interviewId}/cancel`)
  },

  // 从腾讯会议同步真实会议时间与状态
  syncMeeting(interviewId) {
    return request.post(`/interviews/${interviewId}/sync`)
  },

  // 修改已创建的会议（主题、起止时间、密码、等候室、云录制）
  update(interviewId, data) {
    return request.patch(`/interviews/${interviewId}`, data)
  },

  // 读取会议当前云录制/转写设置（修改弹窗初始化用）
  getRecordSettings(interviewId) {
    return request.get(`/interviews/${interviewId}/record-settings`)
  },

  // 上传录音/视频/文档，大文件不限制 axios 超时
  // candidateName 是候选人姓名（判断转写里谁在回答），留空则沿用记录上已有的姓名
  uploadMedia(interviewId, file, candidateName, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    if (candidateName) formData.append('candidate_name', candidateName)
    return api.post(`/interviews/${interviewId}/media`, formData, {
      timeout: 0,
      onUploadProgress: onProgress
    })
  },

  // 指定候选人姓名；姓名变化会作废旧评价，需要重新分析
  updateCandidateName(interviewId, candidateName) {
    return request.patch(`/interviews/${interviewId}/candidate`, { candidate_name: candidateName })
  },

  // 从腾讯会议拉取录制转写
  pullTencent(interviewId, data = {}) {
    return request.post(`/interviews/${interviewId}/transcript/tencent`, data)
  },

  // 触发 / 重试 AI 分析
  analyze(interviewId) {
    return request.post(`/interviews/${interviewId}/analyze`)
  },

  getEvaluation(interviewId) {
    return request.get(`/interviews/${interviewId}/evaluation`)
  },

  // 人工修订评分：只传要改的维度 + 修订原因，服务端保留 AI 原分并重算总分
  updateEvaluation(interviewId, data) {
    return request.patch(`/interviews/${interviewId}/evaluation`, data)
  }
}
