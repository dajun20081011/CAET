import axios from 'axios'
import type { LearnerIssue } from '@/api'
export function learnerError(error: unknown): string {
 const status = axios.isAxiosError(error) ? error.response?.status : undefined
 if (status === 401) return '登录已失效，请重新登录后重试。'
 if (status === 403) return '你没有访问此内容的权限，请联系管理员。'
 if (status === 404 || status === 410) return '内容不存在或已被删除，请返回任务列表。'
 return '网络或服务暂时不可用，请检查连接后重试。'
}
export function confirmedIssues(issues: LearnerIssue[] = []): LearnerIssue[] {
 return issues.filter(issue => issue.issue_status === 'confirmed' && !issue.filter_reason)
}
