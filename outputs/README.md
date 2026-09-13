1. 文件夹用途
   outputs保存可以由代码重新生成的诊断、面板检查、回归表和图。

2. diagnostics
   diagnostics保存数据审计和数量守恒结果。纠正数据的资格结果位于diagnostics/corrected_v1。

3. regression
   回归阶段应分别保存主规格、空间样本、稳健性和异质性结果，并记录对应样本与变量版本。

4. 使用规则
   outputs不提交到Git。重要结果应同时在reports中记录，并能够由冻结数据和版本化代码重新生成。
