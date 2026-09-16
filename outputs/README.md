1. 文件夹用途
outputs保存可以由代码重新生成的诊断、面板检查、回归表和图。
2. diagnostics
diagnostics保存数据审计和数量守恒、身份、日期、地理、空间和回归就绪检查。纠正数据的资格结果位于diagnostics/corrected\_v1。
3. pipeline
保存统一pipeline生成的阶段结果。`pipeline\_runs/`里的`run\_manifest.json`记录每次运行的命令、状态、输入输出路径和SHA256，可用于确认两次运行到底用了什么文件。



