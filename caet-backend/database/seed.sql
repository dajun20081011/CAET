-- ============================================================
-- CAET 种子数据（幂等，可重复执行）
-- 本文件不创建任何账号或密码；管理员由部署环境初始化，其他账号由管理员创建。
-- 课程：broadcast(广播词) / caet2(英文问答) / caet3(中译英)
-- 任务与测评数据由管理员在平台内创建，不写入源码。
-- ============================================================

-- ---------------- 班级 ----------------
INSERT INTO learner_groups (id, name)
VALUES ('aaaaaaaa-0000-0000-0000-0000000000aa', '乘务一班')
ON CONFLICT (id) DO NOTHING;

-- ---------------- 课程 ----------------
INSERT INTO courses (id, code, title, description, course_type, status)
VALUES
  ('b0000000-0000-0000-0000-0000000000b0', 'BROADCAST-01', '客舱广播词训练（Warm Up）', '广播词标准朗读、易错词、重点句型与跟读录音测评。', 'broadcast', 'active'),
  ('c2000000-0000-0000-0000-0000000000c2', 'CAET2-01', 'CAET2 英文问答训练', '英文情景问答，仅英文作答。', 'caet2', 'active'),
  ('c3000000-0000-0000-0000-0000000000c3', 'CAET3-01', 'CAET3 中译英训练', '中文情景提示，翻译为英文。', 'caet3', 'active')
ON CONFLICT (code) DO NOTHING;

-- ---------------- 广播词课程内容（第1章 第1天） ----------------
INSERT INTO course_content (id, course_id, chapter_no, chapter_title, day_no, content_order, content_type, payload)
VALUES
  ('b0000001-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboard', 1, 1, 'explanation',
   '{"text":"本章学习客舱广播的标准开场与欢迎词，注意语速与重音。"}'),
  ('b0000002-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboard', 1, 2, 'sentence',
   '{"id":"w1","zh":"女士们先生们，欢迎登机。","en":"Ladies and gentlemen, welcome aboard.","note":"welcome aboard 为重读短语，注意 aboard 的连读。","audio":null}'),
  ('b0000003-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboard', 1, 3, 'vocabulary',
   '{"items":[{"word":"aboard","phonetic":"/əˈbɔːrd/","meaning":"在（船、飞机）上"},{"word":"boarding","phonetic":"/ˈbɔːrdɪŋ/","meaning":"登机"},{"word":"cabin","phonetic":"/ˈkæbɪn/","meaning":"客舱"}]}'),
  ('b0000004-0000-0000-0000-000000000004', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboard', 1, 4, 'sentence',
   '{"id":"w2","zh":"请您系好安全带。","en":"Please fasten your seat belt.","note":"fasten your seat belt 为安全提示高频句。","audio":null}'),
  ('b0000005-0000-0000-0000-000000000005', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboards', 1, 5, 'practice',
   '{"questions":[{"id":"q1","question":"“欢迎登机”的英文是？","options":["Welcome aboard","Goodbye","Thank you"],"answer":"A"}]}'),
  ('b0000006-0000-0000-0000-000000000006', 'b0000000-0000-0000-0000-0000000000b0', 1, 'Welcome Aboard', 1, 6, 'summary',
   '{"text":"完成跟读录音并提交本篇测评，即可进入下一天训练。"}')
ON CONFLICT (id) DO NOTHING;

-- ---------------- CAET2 课程内容（阅读材料，测评为英文问答） ----------------
INSERT INTO course_content (id, course_id, chapter_no, chapter_title, day_no, content_order, content_type, payload)
VALUES
  ('c2000001-0000-0000-0000-000000000001', 'c2000000-0000-0000-0000-0000000000c2', 1, 'Cabin Service Q&A', 1, 1, 'explanation',
   '{"text":"阅读以下客舱服务情景，准备英文问答测评。"}'),
  ('c2000002-0000-0000-0000-000000000002', 'c2000000-0000-0000-0000-0000000000c2', 1, 'Cabin Service Q&A', 1, 2, 'sentence',
   '{"id":"c2-1","zh":"为乘客提供饮品时如何表达？","en":"Would you like something to drink? We have juice, coffee and tea.","note":"服务用语，注意委婉语气。","audio":null}')
ON CONFLICT (id) DO NOTHING;

-- ---------------- CAET3 课程内容（中译英阅读，测评为中译英） ----------------
INSERT INTO course_content (id, course_id, chapter_no, chapter_title, day_no, content_order, content_type, payload)
VALUES
  ('c3000001-0000-0000-0000-000000000001', 'c3000000-0000-0000-0000-0000000000c3', 1, 'Announcement Translation', 1, 1, 'explanation',
   '{"text":"阅读中文广播提示，准备中译英测评。"}'),
  ('c3000002-0000-0000-0000-000000000002', 'c3000000-0000-0000-0000-0000000000c3', 1, 'Announcement Translation', 1, 2, 'sentence',
   '{"id":"c3-1","zh":"飞机即将起飞，请关闭电子设备。","en":"The aircraft is about to take off, please turn off all electronic devices.","note":"turn off electronic devices 为起飞前标准提示。","audio":null}')
ON CONFLICT (id) DO NOTHING;
