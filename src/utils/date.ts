import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')

export function formatDate(date: string, fmt = 'YYYY年MM月DD日'): string {
  return dayjs(date).format(fmt)
}

export function formatDateShort(date: string): string {
  return dayjs(date).format('YYYY-MM-DD')
}
