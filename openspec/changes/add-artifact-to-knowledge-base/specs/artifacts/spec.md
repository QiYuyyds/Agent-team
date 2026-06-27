## ADDED Requirements

### Requirement: 产物库 SHALL 为 document 类型产物提供「加入知识库」操作

产物库界面 MUST 为 `type === 'document'` 的产物项提供「加入知识库」操作入口（与现有删除操作同处 hover 操作区）。该入口 MUST NOT 出现在其他类型（`web_app`、`code_file`、`diff`、`image`、`ppt`、`diagram`、`project`）的产物项上。

#### Scenario: document 产物显示入口
- **WHEN** 产物库渲染一个 `type='document'` 的产物项
- **THEN** 该项的操作区显示「加入知识库」按钮

#### Scenario: 非 document 产物不显示入口
- **WHEN** 产物库渲染一个非 `document` 类型的产物项
- **THEN** 该项 MUST NOT 显示「加入知识库」按钮

#### Scenario: 点击入库并反馈
- **WHEN** 用户点击「加入知识库」
- **THEN** 系统按需拉取产物完整内容并发起入库
- **AND** 入库进行中按钮处于 loading 态以防重复点击
- **AND** 结果以 toast 反馈：成功 / 已在知识库中 / 失败原因
