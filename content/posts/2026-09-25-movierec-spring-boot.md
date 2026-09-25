---
title: MovieRec：用 Spring Boot 构建电影推荐后端
date: 2026-09-25
tags: [项目实战, Java, Spring Boot, 电影推荐]
excerpt: 从电影检索、评分收藏到推荐列表和 AI 客服，梳理我的 MovieRec 后端项目：功能如何组织、推荐结果如何返回，以及下一步值得完善的地方。
---

找一部想看的电影，可能从一个片名开始，也可能只是一个模糊的念头：想看科幻片，想找某位导演的作品，或者想知道喜欢的电影还有哪些同类推荐。

**MovieRec** 是我的电影推荐项目。它围绕电影发现和用户互动提供一组后端接口，把检索、筛选、评分、收藏、评论和推荐列表组织在一起。这篇文章记录当前仓库里的实现，重点放在功能背后的数据流和几个具体的处理细节。

[查看 MovieRec 的 GitHub 仓库 ↗](https://github.com/E1zGo/movierec)

## 项目做了什么

当前仓库主要包含 Java 后端代码。围绕“找到电影，再留下自己的反馈”，功能可以分成四组：

| 模块 | 当前提供的能力 |
| --- | --- |
| 电影发现 | 分页列表、电影详情、热门电影、关键词搜索、类型与年代筛选 |
| 用户互动 | 评分与修改评分、收藏与取消收藏、分享计数、评论和回复、举报 |
| 推荐列表 | 按用户读取推荐记录、获取最新推荐、电影详情中的同类型推荐 |
| 使用帮助 | 常见问题、接入 DeepSeek 的客服问答、接口失败时的预设回复 |

这里的“推荐”需要分开理解：用户推荐接口负责读取已经存储的推荐记录；详情页的相关推荐则通过电影类型寻找候选。本文涉及的服务代码并没有展示推荐模型的训练或推荐分数的生成流程。

## 用清晰的分层组织功能

项目使用 **Java 17、Spring Boot 3.2.0、Spring Data JPA 和 MySQL**，通过 Maven 管理依赖，Lombok 减少实体类的样板代码。具体依赖可以在 [pom.xml](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/pom.xml) 中查看。

一次典型的请求会经过这样的路径：

```text
客户端请求
    ↓
Controller：接收参数、返回接口结果
    ↓
Service：组织业务逻辑、转换返回数据
    ↓
Repository：查询或更新数据
    ↓
MySQL
```

`Movie` 是电影数据的核心实体，除了片名、导演、上映日期和海报地址，还维护平均评分、评分人数、分享次数等字段。电影与演员、类型之间通过关联表建立多对多关系，评分、收藏和评论则分别用独立实体记录。

接口通常使用 DTO 返回页面需要的字段。例如，`MovieDTO` 会把演员和类型转换成名称列表；轻量搜索使用 `MovieSearchDTO`，只保留电影 ID、片名、海报、上映日期、平均评分和简介。相比直接返回完整实体，这种区分让接口的数据范围更清楚。

相关实现见 [Movie 实体](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/entity/Movie.java) 和 [MovieService](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/service/MovieService.java)。

## 搜索：从一个关键词到一组条件

电影搜索不只匹配标题。`MovieRepository` 中的综合查询同时检查**片名、导演、类型名称和演员名称**，使用 `LEFT JOIN` 连接关联数据，再用 `DISTINCT` 避免同一部电影因多个匹配项重复出现。

搜索接口分为完整结果和轻量结果，两者都支持分页。类型与年代筛选则走另一条路径：服务层拆分逗号分隔的类型，把 `2010s` 转换为 2010—2019 年，再交给 Repository 查询。

多选类型采用“同时满足”的思路。查询先筛出所选类型，再按电影分组，通过 `HAVING` 中的匹配数量判断电影是否包含全部选中类型。例如同时选择“科幻”和“动作”，目标是找到两种类型都具备的电影。

搜索历史也做了几个小处理：去除输入两端的空格、忽略空查询、按大小写不敏感的方式移除旧记录，再把本次搜索放到最前面，最多保留 8 条。

这些逻辑分别位于 [MovieRepository](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/repository/MovieRepository.java) 与 [SearchService](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/service/SearchService.java)。

## 评分与收藏：让反馈同步到电影信息

用户再次给同一部电影评分时，服务会查找已有的用户—电影评分记录。有记录就更新，没有记录才新增，然后重新读取这部电影的评分，计算平均值并更新评分人数。

平均值使用 `BigDecimal` 计算，保留两位小数，采用 `HALF_UP` 舍入。评分写入和电影统计更新放在同一个事务方法中，让这次操作作为一个整体执行。这里处理的是单次操作的事务边界；多用户并发更新时的统计一致性，仍需要进一步考虑。

收藏接口返回的信息也不只是一句“成功”。它会在切换收藏状态后，一起返回：

- `message`：本次操作的提示。
- `isFavorited`：操作后的收藏状态。
- `newFavoriteCount`：最新的收藏总数。

这样客户端可以直接根据返回结果刷新按钮和计数，不必自己猜测状态。

对应源码是 [UserMovieRatingService](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/service/UserMovieRatingService.java) 与 [UserMovieFavoriteService](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/service/UserMovieFavoriteService.java)。

## 推荐列表：排序、去重和空结果兜底

用户推荐主要提供两个入口：

| 接口 | 排序与数量 |
| --- | --- |
| `GET /api/recommendations/user/{userId}` | 按推荐分数降序、推荐时间降序读取，默认最多查询 25 条记录 |
| `GET /api/recommendations/latest/{userId}` | 按推荐时间降序读取，默认最多查询 10 条记录 |

两者都从 `RecommendationLog` 读取数据。如果没有记录，就返回热门电影作为兜底。这里的热门电影要求评分人数大于零，先按平均评分排序，再按评分人数排序。

读到推荐日志后，服务会转换为电影 DTO，并按电影 ID 去重。核心片段如下：

```java
Set<Integer> uniqueMovieIds = new HashSet<>();
return logs.stream()
        .map(log -> movieService.convertToDTO(log.getMovie()))
        .filter(dto -> uniqueMovieIds.add(dto.getMovieId()))
        .collect(Collectors.toList());
```

`Set.add()` 只有在第一次遇到这个 ID 时才返回 `true`，因此可以保留排序结果中第一次出现的电影。

这里还有一个值得注意的边界：**查询数量限制发生在去重之前**。如果前 25 条日志包含重复电影，最终列表可能不足 25 部。目前代码不会在去重后自动补足；后续可以考虑在查询阶段去重，或者分批获取候选，直到满足所需数量。

电影详情的相关推荐使用另一种规则：找到与当前电影有共同类型的影片，排除当前电影，再按平均评分和评分人数排序，接口请求 6 部候选。

这部分实现可以对照 [RecommendationService](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/service/RecommendationService.java) 和 [RecommendationLogRepository](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/repository/RecommendationLogRepository.java) 阅读。

## AI 客服：把外部能力放在明确的位置

`SupportController` 提供 `POST /api/support/ai-chat` 接口，接收用户问题，在后端调用 DeepSeek 的 `deepseek-chat` 模型。系统提示将助手的职责限定为电影平台的使用帮助，例如账户、资料修改和电影收藏等问题。

当前请求由系统提示和本次问题组成，没有在这个接口里维护多轮会话历史。如果外部接口调用失败，代码会根据关键词返回预设回复，并标注当前使用离线模式。

因此，这部分 AI 能力属于**客服问答**。它与前面的推荐日志读取是两条独立的数据流，不能仅因为项目接入了大模型，就把电影列表描述成由大模型实时生成的推荐。

相关实现见 [SupportController](https://github.com/E1zGo/movierec/blob/c8bff516d80e789516bace8936347648de4fd85d/src/main/java/com/example/movierec/controller/SupportController.java)。

## 下一步值得完善的地方

在当前实现之上，我认为最值得继续打磨的是以下几个方向：

1. **明确推荐数据的生成过程。** 为推荐日志补充可追踪的来源和更新方式，再通过测试或评估数据判断推荐效果。
2. **处理列表边界。** 包括去重后补足推荐数量、统一分页返回结构，以及对 `page`、`size`、`limit` 设置合理范围。
3. **减少重复查询。** 当前电影 DTO 转换会逐部查询收藏数量；可以考虑批量聚合，并检查关联数据加载带来的额外查询。
4. **完善评分与交互的一致性。** 当前评分统计会重新读取全部评分，可进一步研究数据库聚合、唯一约束及并发更新策略。
5. **为真实运行补齐保障。** 统一身份与权限校验、请求参数验证和错误处理，为外部 AI 请求配置超时，并补充核心业务的自动化测试。

整理 MovieRec 时，值得留下的不只是接口列表，还有这些连接功能的细节：用户重复评分该怎样处理，推荐没有数据时返回什么，同一部电影为什么会重复出现，外部服务失效后页面还能提供哪些帮助。

把这些问题讲清楚，也就有了继续改进项目的起点。

---

本文根据仓库 `master` 分支的 [c8bff51 版本](https://github.com/E1zGo/movierec/tree/c8bff516d80e789516bace8936347648de4fd85d) 整理，描述的是代码中的实现与待改进方向，未对项目进行部署或性能测试。
