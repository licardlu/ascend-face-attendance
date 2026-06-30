# 基于昇腾310B的人脸识别打卡系统

这是课程设计项目仓库，基于教师提供的 `Ascend310-main/samples/case1` 人脸打卡例程整理。

## 目录说明

- `src/case1/`：人脸注册、人脸识别、考勤记录相关代码
- `docs/课程设计计划书.pdf`：课程设计计划书

## 板端运行提示

在昇腾310B板端进入 `src/case1` 后运行：

```bash
source /usr/local/Ascend/ascend-toolkit/set_env.sh
python3 app.py
```

浏览器访问：

```text
http://板子IP:5000
```

## 注意事项

- 模型文件、数据库、上传图片、运行日志不放入 Git 仓库。
- 若需要重新部署到板子，需要按教师手册准备 ONNX/OM 模型文件。
