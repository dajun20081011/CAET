#!/usr/bin/env node
/**
 * 导入课程数据到 Supabase
 * 用法: node scripts/import-course.js <course-data-file.json>
 */

const fs = require('fs')
const path = require('path')

async function importCourse(filePath) {
  const data = JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  
  console.log('课程:', data.course_code)
  console.log('章节:', data.chapter_title)
  console.log('天数:', data.days.length)
  
  // 输出 SQL INSERT 语句供手动执行
  console.log('\n-- 执行以下 SQL 导入课程数据到 Supabase:')
  
  data.days.forEach((day, dayIdx) => {
    day.blocks.forEach((block, blockIdx) => {
      const payload = JSON.stringify(block).replace(/'/g, "''")
      console.log(`INSERT INTO course_content (course_id, chapter_no, chapter_title, day_no, content_order, content_type, payload) VALUES (
        (SELECT id FROM courses WHERE code = '${data.course_code}'),
        ${data.chapter},
        '${data.chapter_title}',
        ${day.day},
        ${blockIdx},
        '${block.type}',
        '${payload}'::jsonb
      );`)
    })
  })
  
  console.log('\n-- 或使用 Supabase Dashboard 的 Table Editor 手动导入')
}

const file = process.argv[2]
if (!file) {
  console.log('用法: node scripts/import-course.js <course-data-file.json>')
  process.exit(1)
}

importCourse(path.resolve(file))
