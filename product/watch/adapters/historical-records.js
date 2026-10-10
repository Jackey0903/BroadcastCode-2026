// Read-only extracts of the two accepted 2026-10-07 runs. Never initiate a new job.
export const historicalRecords = [
  {
    "verifiedAt": "2026-10-07T12:02:10.035692+00:00",
    "jobId": "81a74837370e46a890cbacb2069074e6",
    "sample": "flagg",
    "mode": "story",
    "outputSha256": "e1b390b689d43b48bdbfb6054111e34b1b785697f16b3b9e90f8aff6afbdf3d9",
    "bytes": 9997821,
    "durationSeconds": 21.548005,
    "width": 1280,
    "height": 900,
    "audioPresent": true,
    "rangeStatus": 206,
    "modelId": "global.anthropic.claude-sonnet-4-6",
    "elapsedSeconds": 62.81,
    "browserPlaybackVerified": true,
    "burnedOverlayVisuallyVerified": true,
    "contentReview": {
      "acceptedForShowcase": true,
      "reviewer": "AI assistant; not human expert certification",
      "reviewedAt": "2026-10-07T12:04:29.638323+00:00",
      "findings": [
        "Compared final generated plan and rendered frames with registered source observations and official event.",
        "Official event and xFG copied unchanged; no invented quantitative, causal or UI-direction claims found."
      ],
      "minorPresentationIssue": null
    },
    "recordSource": "BroadcastCode-2026/product/evidence/run-81a74837370e46a890cbacb2069074e6.json",
    "recordSha256": "f51d28ec69f4388521790db32c461032c6411b27e729009df6e92138b069c96e",
    "historical": true,
    "localMediaAvailable": false,
    "analysis": {
      "scope": "product_story_protocol_not_organizer_evaluation_schema",
      "summary": "末节落后局面下，弗拉格持球推进至禁区附近，在正面防守人双臂举起的情况下完成挑篮，官方记录命中。",
      "plan": {
        "perspective": "player",
        "metrics": [
          {
            "eventId": 666.0,
            "revealAt": 18.5,
            "display": "51.0%",
            "barRatio": 0.51,
            "definition": "NBA 官方对本次出手机会的概率型参考值；不是这个球员的个人命中率或胜率。",
            "playerId": "1642843",
            "rawValue": 0.51,
            "label": "预期投篮命中率",
            "unit": "ratio",
            "id": "flagg-shot-metric",
            "evidenceId": "flagg-xfg-666",
            "sourceUrl": "https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500701&playerId=1642843",
            "gameId": "0022500701"
          }
        ],
        "title": "弗拉格：禁区附近的终结",
        "chapters": [
          {
            "focus": "持球人位置与比分",
            "id": "context",
            "title": "先看局面",
            "end": 9.0,
            "caption": "末节，独行侠落后，弗拉格持球准备推进。",
            "evidenceIds": [
              "flagg-frame-0-2"
            ],
            "start": 0.0
          },
          {
            "id": "approach",
            "end": 15.5,
            "caption": "弗拉格持球向禁区附近推进，防守人在其身前。",
            "title": "推进至禁区附近",
            "evidenceIds": [
              "flagg-frame-9",
              "flagg-frame-15-5",
              "flagg-roster",
              "frame-12000",
              "frame-15500"
            ],
            "start": 9.0,
            "focus": "弗拉格持球推进"
          },
          {
            "caption": "弗拉格在篮下起跳，正面防守人双臂已举起。",
            "focus": "起跳与防守人姿态",
            "evidenceIds": [
              "flagg-frame-16-5",
              "flagg-frame-17",
              "frame-16000",
              "frame-17000"
            ],
            "start": 15.5,
            "id": "key-beat",
            "title": "篮下起跳这一拍",
            "end": 17.5
          },
          {
            "start": 17.5,
            "title": "官方数据回看机会",
            "end": 21.548,
            "id": "record",
            "evidenceIds": [
              "flagg-pbp-666",
              "flagg-xfg-666",
              "frame-18000"
            ],
            "caption": "官方确认命中；出手机会质量见官方出手数据指标。",
            "focus": "命中结果与机会质量"
          }
        ],
        "associationMethod": "curated_practice_video_mapping_not_automatic_event_matching",
        "summary": "末节落后局面下，弗拉格持球推进至禁区附近，在正面防守人双臂举起的情况下完成挑篮，官方记录命中。"
      },
      "observations": [
        {
          "timeSeconds": 0.0,
          "evidenceIds": [
            "flagg-frame-0-2"
          ],
          "text": "末节，独行侠落后，弗拉格持球准备推进。"
        },
        {
          "text": "弗拉格持球向禁区附近推进，防守人在其身前。",
          "timeSeconds": 9.0,
          "evidenceIds": [
            "flagg-frame-9",
            "flagg-frame-15-5",
            "flagg-roster",
            "frame-12000",
            "frame-15500"
          ]
        },
        {
          "text": "弗拉格在篮下起跳，正面防守人双臂已举起。",
          "timeSeconds": 15.5,
          "evidenceIds": [
            "flagg-frame-16-5",
            "flagg-frame-17",
            "frame-16000",
            "frame-17000"
          ]
        },
        {
          "text": "官方确认命中；出手机会质量见官方出手数据指标。",
          "timeSeconds": 17.5,
          "evidenceIds": [
            "flagg-pbp-666",
            "flagg-xfg-666",
            "frame-18000"
          ]
        }
      ],
      "preservesSourceTimeline": true,
      "protocol_version": "product-story-v1",
      "source_frame_times_ms": [
        3000.0,
        12000.0,
        15500.0,
        16000.0,
        17000.0,
        18000.0
      ],
      "validation": {
        "protocol": "product-story-v1",
        "checks": [
          "known_evidence_ids",
          "cited_frames_actually_inspected",
          "source_time_bounds",
          "nonoverlapping_chapters",
          "no_model_authored_numbers",
          "official_metrics_copied_verbatim",
          "known_causal_static_phrases_rejected",
          "court_location_vocabulary_from_source_text",
          "no_guessed_metric_layout_positions"
        ],
        "chapterCount": 4.0,
        "sourceDurationMs": 21548.118,
        "inspectedFrameIds": [
          "frame-12000",
          "frame-15500",
          "frame-16000",
          "frame-17000",
          "frame-18000",
          "frame-3000"
        ],
        "passed": true,
        "scope": "Structural and provenance validation; not an independent factual or basketball-accuracy certification"
      },
      "evidence": [
        {
          "sourceUrl": "/samples/flagg.mp4#t=0.2",
          "humanExpertReviewed": false,
          "scoreboard": {
            "score": {
              "HOU": 107.0,
              "DAL": 103.0
            },
            "clock": "1:51"
          },
          "kind": "observation",
          "title": "画面 · 0.2 秒",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "id": "flagg-frame-0-2",
          "frameUrl": "/frames/flagg-00.2s.jpg",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "body": "第四节，独行侠落后四分。",
          "videoTime": 0.2,
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。",
          "description": "第四节，独行侠落后四分。"
        },
        {
          "scoreboard": {
            "clock": "1:43"
          },
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "frameUrl": "/frames/flagg-09s.jpg",
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。",
          "humanExpertReviewed": false,
          "description": "深衣 32 号持球，附近有深衣 21 号及白衣防守人。",
          "kind": "observation",
          "id": "flagg-frame-9",
          "sourceUrl": "/samples/flagg.mp4#t=9",
          "title": "画面 · 9 秒",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "body": "深衣 32 号持球，附近有深衣 21 号及白衣防守人。",
          "videoTime": 9.0
        },
        {
          "sourceUrl": "/samples/flagg.mp4#t=15.5",
          "videoTime": 15.5,
          "body": "32 号已推进到禁区附近，防守人在其身前和侧后方。",
          "frameUrl": "/frames/flagg-15.5s.jpg",
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。",
          "description": "32 号已推进到禁区附近，防守人在其身前和侧后方。",
          "kind": "observation",
          "scoreboard": {
            "clock": "1:36"
          },
          "humanExpertReviewed": false,
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "id": "flagg-frame-15-5",
          "title": "画面 · 15.5 秒",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip"
        },
        {
          "videoTime": 16.5,
          "description": "32 号在篮下起跳，正面白衣防守人双臂举起。",
          "frameUrl": "/frames/flagg-16.5s.jpg",
          "scoreboard": {
            "clock": "1:35"
          },
          "id": "flagg-frame-16-5",
          "sourceUrl": "/samples/flagg.mp4#t=16.5",
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "humanExpertReviewed": false,
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "kind": "observation",
          "title": "画面 · 16.5 秒",
          "body": "32 号在篮下起跳，正面白衣防守人双臂举起。"
        },
        {
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "body": "球已离开出手者双手；底部和篮架时钟存在显示差异。",
          "sourceUrl": "/samples/flagg.mp4#t=17",
          "title": "画面 · 17 秒",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "frameUrl": "/frames/flagg-17.0s.jpg",
          "id": "flagg-frame-17",
          "kind": "observation",
          "videoTime": 17.0,
          "humanExpertReviewed": false,
          "scoreboard": {
            "clock": "1:35"
          },
          "description": "球已离开出手者双手；底部和篮架时钟存在显示差异。",
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。"
        },
        {
          "annotationMethod": "AI 助手查看 0.2、9、15.5、16.5、17、21 秒抽帧，记录号码、节次、比赛时钟及比分；16.5 秒为编辑选定慢看节点，非精确离手帧。",
          "body": "比分更新，火箭准备继续进攻。",
          "title": "画面 · 21 秒",
          "description": "比分更新，火箭准备继续进攻。",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "id": "flagg-frame-21",
          "videoTime": 21.0,
          "sourceUrl": "/samples/flagg.mp4#t=21",
          "kind": "observation",
          "humanExpertReviewed": false,
          "frameUrl": "/frames/flagg-21s.jpg",
          "scoreboard": {
            "clock": "1:34",
            "score": {
              "DAL": 105.0,
              "HOU": 107.0
            }
          }
        },
        {
          "kind": "official",
          "title": "NBA 官方逐回合记录",
          "playerId": "1642843",
          "videoTimeMeaning": "编辑选择的数据揭示节点，不是官方出手时钟的逐帧换算。",
          "gameId": "0022500701",
          "actionId": 498.0,
          "id": "flagg-pbp-666",
          "period": 4.0,
          "actionNumber": 666.0,
          "officialClock": "1:34",
          "body": "末节 1:34，弗拉格突破挑篮命中两分，独行侠追至 105 比 107。",
          "eventId": 666.0,
          "sourcePath": "playByPlay.actions[actionNumber=666 & isFieldGoal=1]",
          "description": "末节 1:34，弗拉格突破挑篮命中两分，独行侠追至 105 比 107。",
          "sourceLabel": "NBA.com · Play-by-Play",
          "sourceUrl": "https://www.nba.com/game/dal-vs-hou-0022500701/play-by-play",
          "videoTime": 18.5
        },
        {
          "gameId": "0022500701",
          "id": "flagg-xfg-666",
          "eventId": 666.0,
          "kind": "official",
          "playerId": "1642843",
          "definitionUrl": "https://china.nba.cn/inside-the-game/glossary",
          "display": "51.0%",
          "sourcePath": "data.shotList[eventId=666].value",
          "sourceUrl": "https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500701&playerId=1642843",
          "body": "NBA 中国官网这次出手的原始数值为 0.51，换算显示为 51.0%。这是机会质量的参考，不是球员的个人命中保证。",
          "title": "这次出手的预期投篮命中率",
          "unit": "ratio",
          "value": 0.51,
          "description": "NBA 中国官网这次出手的原始数值为 0.51，换算显示为 51.0%。这是机会质量的参考，不是球员的个人命中保证。",
          "videoTime": 18.5,
          "sourceLabel": "NBA 中国 · 逐次出手数据"
        },
        {
          "id": "flagg-roster",
          "description": "NBA 本场名单：独行侠 32 号为库珀·弗拉格，与所查看画面号码一致。",
          "sourceLabel": "NBA.com · 本场名单",
          "playerId": "1642843",
          "sourceUrl": "https://www.nba.com/game/dal-vs-hou-0022500701/play-by-play",
          "title": "本场身份与号码核对",
          "body": "NBA 本场名单：独行侠 32 号为库珀·弗拉格，与所查看画面号码一致。",
          "gameId": "0022500701",
          "kind": "official",
          "sourcePath": "game.homeTeamPlayers / game.awayTeamPlayers"
        },
        {
          "timestampMs": 3000.0,
          "id": "frame-3000",
          "kind": "video_frame",
          "title": "本次实际输入帧",
          "sourceLabel": "原始视频抽帧",
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-03s.jpg",
          "timeSeconds": 3.0,
          "description": "本次实际输入帧",
          "videoTime": 3.0
        },
        {
          "videoTime": 12.0,
          "timestampMs": 12000.0,
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-12s.jpg",
          "description": "本次实际输入帧",
          "id": "frame-12000",
          "timeSeconds": 12.0,
          "sourceLabel": "原始视频抽帧",
          "title": "本次实际输入帧",
          "kind": "video_frame"
        },
        {
          "timeSeconds": 15.5,
          "sourceLabel": "原始视频抽帧",
          "kind": "video_frame",
          "description": "本次实际输入帧",
          "timestampMs": 15500.0,
          "id": "frame-15500",
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-15.5s.jpg",
          "title": "本次实际输入帧",
          "videoTime": 15.5
        },
        {
          "timestampMs": 16000.0,
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-16.0s.jpg",
          "description": "本次实际输入帧",
          "kind": "video_frame",
          "title": "本次实际输入帧",
          "timeSeconds": 16.0,
          "id": "frame-16000",
          "sourceLabel": "原始视频抽帧",
          "videoTime": 16.0
        },
        {
          "sourceLabel": "原始视频抽帧",
          "id": "frame-17000",
          "description": "本次实际输入帧",
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-17.0s.jpg",
          "timeSeconds": 17.0,
          "videoTime": 17.0,
          "title": "本次实际输入帧",
          "kind": "video_frame",
          "timestampMs": 17000.0
        },
        {
          "timeSeconds": 18.0,
          "title": "本次实际输入帧",
          "videoTime": 18.0,
          "description": "本次实际输入帧",
          "sourceLabel": "原始视频抽帧",
          "id": "frame-18000",
          "kind": "video_frame",
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/flagg-18s.jpg",
          "timestampMs": 18000.0
        }
      ],
      "trace": [
        {
          "step": 1.0,
          "round": 1.0,
          "tool": "inspect_frames",
          "status": "succeeded",
          "elapsedMs": 585.0
        },
        {
          "step": 2.0,
          "round": 1.0,
          "tool": "read_official_event",
          "status": "succeeded",
          "elapsedMs": 25.0
        },
        {
          "step": 3.0,
          "round": 2.0,
          "tool": "validate_story",
          "status": "rejected",
          "elapsedMs": 3.0
        },
        {
          "step": 4.0,
          "round": 3.0,
          "tool": "validate_story",
          "status": "succeeded",
          "elapsedMs": 1.0
        }
      ]
    }
  },
  {
    "verifiedAt": "2026-10-07T12:03:25.789662+00:00",
    "jobId": "ce008e75d25d4e2e8e88b57412f6c762",
    "sample": "amen",
    "mode": "story",
    "outputSha256": "8b0a20d36e5f63898e3c36676f3d491164ae77fe3aafc292b15fb6f7d178033f",
    "bytes": 14989055,
    "durationSeconds": 22.895011,
    "width": 1280,
    "height": 900,
    "audioPresent": true,
    "rangeStatus": 206,
    "modelId": "global.anthropic.claude-sonnet-4-6",
    "elapsedSeconds": 59.39,
    "browserPlaybackVerified": true,
    "burnedOverlayVisuallyVerified": true,
    "contentReview": {
      "acceptedForShowcase": true,
      "reviewer": "AI assistant; not human expert certification",
      "reviewedAt": "2026-10-07T12:04:29.638323+00:00",
      "findings": [
        "Compared final generated plan and rendered frames with registered source observations and official event.",
        "Official event and xFG copied unchanged; no invented quantitative, causal or UI-direction claims found."
      ],
      "minorPresentationIssue": null
    },
    "recordSource": "BroadcastCode-2026/product/evidence/run-ce008e75d25d4e2e8e88b57412f6c762.json",
    "recordSha256": "bad70f2540cd962f29d57befb5bd07b7da8e139a53516d96ad92a28c48ed2027",
    "historical": true,
    "localMediaAvailable": false,
    "analysis": {
      "scope": "product_story_protocol_not_organizer_evaluation_schema",
      "summary": "进攻时钟告急，阿门接球推进。克里斯蒂先行起跳，阿门仍持球；随后阿门起跳出手，克里斯蒂已在下落。官方确认这球命中，杜兰特记录助攻。",
      "plan": {
        "title": "先起跳的防守人",
        "summary": "进攻时钟告急，阿门接球推进。克里斯蒂先行起跳，阿门仍持球；随后阿门起跳出手，克里斯蒂已在下落。官方确认这球命中，杜兰特记录助攻。",
        "chapters": [
          {
            "id": "transfer",
            "start": 15.0,
            "end": 16.8,
            "focus": "阿门持球推进",
            "title": "球来到阿门手中",
            "caption": "杜兰特传出，阿门接球，进攻时钟所剩不多。",
            "evidenceIds": [
              "frame-15000",
              "frame-16000",
              "amen-roster"
            ]
          },
          {
            "focus": "起跳先后顺序",
            "end": 18.5,
            "evidenceIds": [
              "frame-17500",
              "frame-18000",
              "amen-roster"
            ],
            "id": "key-beat",
            "caption": "克里斯蒂已起跳，阿门仍持球；随后阿门起跳，克里斯蒂正在下落。",
            "title": "慢看这一拍",
            "start": 16.8
          },
          {
            "id": "record",
            "title": "官方记录与出手数据",
            "focus": "官方结果与指标",
            "caption": "官方确认命中，杜兰特记录助攻；出手机会质量见官方出手数据指标。",
            "start": 18.5,
            "end": 22.894,
            "evidenceIds": [
              "amen-pbp-396",
              "amen-xfg-396"
            ]
          }
        ],
        "metrics": [
          {
            "id": "amen-shot-metric",
            "rawValue": 0.445,
            "display": "44.5%",
            "gameId": "0022500491",
            "playerId": "1641708",
            "definition": "NBA 官方对本次出手机会的概率型参考值；不是这个球员的个人命中率或胜率。",
            "sourceUrl": "https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500491&playerId=1641708",
            "revealAt": 19.5,
            "eventId": 396.0,
            "barRatio": 0.445,
            "unit": "ratio",
            "label": "预期投篮命中率",
            "evidenceId": "amen-xfg-396"
          }
        ],
        "associationMethod": "curated_practice_video_mapping_not_automatic_event_matching",
        "perspective": "defender"
      },
      "observations": [
        {
          "timeSeconds": 15.0,
          "evidenceIds": [
            "frame-15000",
            "frame-16000",
            "amen-roster"
          ],
          "text": "杜兰特传出，阿门接球，进攻时钟所剩不多。"
        },
        {
          "timeSeconds": 16.8,
          "evidenceIds": [
            "frame-17500",
            "frame-18000",
            "amen-roster"
          ],
          "text": "克里斯蒂已起跳，阿门仍持球；随后阿门起跳，克里斯蒂正在下落。"
        },
        {
          "text": "官方确认命中，杜兰特记录助攻；出手机会质量见官方出手数据指标。",
          "evidenceIds": [
            "amen-pbp-396",
            "amen-xfg-396"
          ],
          "timeSeconds": 18.5
        }
      ],
      "preservesSourceTimeline": true,
      "protocol_version": "product-story-v1",
      "source_frame_times_ms": [
        12000.0,
        15000.0,
        16000.0,
        17000.0,
        17500.0,
        18000.0
      ],
      "validation": {
        "checks": [
          "known_evidence_ids",
          "cited_frames_actually_inspected",
          "source_time_bounds",
          "nonoverlapping_chapters",
          "no_model_authored_numbers",
          "official_metrics_copied_verbatim",
          "known_causal_static_phrases_rejected",
          "court_location_vocabulary_from_source_text",
          "no_guessed_metric_layout_positions"
        ],
        "scope": "Structural and provenance validation; not an independent factual or basketball-accuracy certification",
        "chapterCount": 3.0,
        "protocol": "product-story-v1",
        "sourceDurationMs": 22894.875,
        "passed": true,
        "inspectedFrameIds": [
          "frame-12000",
          "frame-15000",
          "frame-16000",
          "frame-17000",
          "frame-17500",
          "frame-18000"
        ]
      },
      "evidence": [
        {
          "description": "第三节，火箭落后三分。",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "videoTime": 0.0,
          "id": "amen-frame-0",
          "body": "第三节，火箭落后三分。",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "humanExpertReviewed": false,
          "sourceUrl": "/samples/amen.mp4#t=0",
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "kind": "observation",
          "title": "画面 · 0 秒",
          "scoreboard": {
            "score": {
              "HOU": 60.0,
              "DAL": 63.0
            },
            "clock": "7:45"
          },
          "frameUrl": "/frames/amen-00s.jpg"
        },
        {
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "videoTime": 15.0,
          "description": "白衣 7 号持球，深衣 00 号在正面，3 号靠近。",
          "kind": "observation",
          "frameUrl": "/frames/amen-15s.jpg",
          "sourceUrl": "/samples/amen.mp4#t=15",
          "scoreboard": {
            "clock": "7:30",
            "shotClock": "4.5"
          },
          "humanExpertReviewed": false,
          "title": "画面 · 15 秒",
          "body": "白衣 7 号持球，深衣 00 号在正面，3 号靠近。",
          "id": "amen-frame-15"
        },
        {
          "body": "白衣 1 号持球，球已从先前的 7 号手中转移。",
          "title": "画面 · 16 秒",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "sourceUrl": "/samples/amen.mp4#t=16",
          "frameUrl": "/frames/amen-16.0s.jpg",
          "description": "白衣 1 号持球，球已从先前的 7 号手中转移。",
          "kind": "observation",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "videoTime": 16.0,
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "humanExpertReviewed": false,
          "id": "amen-frame-16",
          "scoreboard": {
            "clock": "7:29",
            "shotClock": "3.5"
          }
        },
        {
          "videoTime": 17.5,
          "sourceUrl": "/samples/amen.mp4#t=17.5",
          "title": "画面 · 17.5 秒",
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "humanExpertReviewed": false,
          "scoreboard": {
            "shotClock": "2.1",
            "clock": "7:27"
          },
          "description": "深衣 00 号已起跳，白衣 1 号仍持球。",
          "id": "amen-frame-17-5",
          "body": "深衣 00 号已起跳，白衣 1 号仍持球。",
          "frameUrl": "/frames/amen-17.5s.jpg",
          "kind": "observation",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧"
        },
        {
          "humanExpertReviewed": false,
          "id": "amen-frame-18",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "kind": "observation",
          "body": "白衣 1 号起跳投篮，深衣 00 号正在下落。",
          "videoTime": 18.0,
          "frameUrl": "/frames/amen-18s.jpg",
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "sourceUrl": "/samples/amen.mp4#t=18",
          "description": "白衣 1 号起跳投篮，深衣 00 号正在下落。",
          "scoreboard": {
            "shotClock": "1.6",
            "clock": "7:27"
          },
          "title": "画面 · 18 秒",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧"
        },
        {
          "videoTime": 21.0,
          "kind": "observation",
          "body": "火箭得分更新为 62，独行侠仍为 63。",
          "sourceLabel": "主办方公开训练视频 · 已查看抽帧",
          "sourceUrl": "/samples/amen.mp4#t=21",
          "annotationMethod": "AI 助手查看 0、15、16、17.5、18、21 秒抽帧，记录号码、节次、比赛时钟及比分；17.5 秒为编辑选定慢看节点，非精确离手帧。",
          "id": "amen-frame-21",
          "originalSourceUrl": "https://comfile.csdnimg.cn/file/train_video.zip",
          "humanExpertReviewed": false,
          "scoreboard": {
            "score": {
              "HOU": 62.0,
              "DAL": 63.0
            },
            "clock": "7:24"
          },
          "description": "火箭得分更新为 62，独行侠仍为 63。",
          "frameUrl": "/frames/amen-21s.jpg",
          "title": "画面 · 21 秒"
        },
        {
          "videoTime": 19.5,
          "sourcePath": "playByPlay.actions[actionNumber=396 & isFieldGoal=1]",
          "body": "第三节 7:25，阿门·汤普森急停跳投命中两分，官方记录杜兰特助攻；火箭追至 62 比 63。",
          "eventId": 396.0,
          "videoTimeMeaning": "编辑选择的数据揭示节点，不是官方出手时钟的逐帧换算。",
          "description": "第三节 7:25，阿门·汤普森急停跳投命中两分，官方记录杜兰特助攻；火箭追至 62 比 63。",
          "actionNumber": 396.0,
          "sourceLabel": "NBA.com · Play-by-Play",
          "actionId": 285.0,
          "title": "NBA 官方逐回合记录",
          "id": "amen-pbp-396",
          "gameId": "0022500491",
          "kind": "official",
          "sourceUrl": "https://www.nba.com/game/hou-vs-dal-0022500491/play-by-play",
          "playerId": "1641708",
          "officialClock": "7:25",
          "period": 3.0
        },
        {
          "unit": "ratio",
          "playerId": "1641708",
          "sourcePath": "data.shotList[eventId=396].value",
          "kind": "official",
          "id": "amen-xfg-396",
          "definitionUrl": "https://china.nba.cn/inside-the-game/glossary",
          "description": "NBA 中国官网这次出手的原始数值为 0.445，换算显示为 44.5%。这是机会质量的参考，不是球员的个人命中保证。",
          "videoTime": 19.5,
          "sourceUrl": "https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId=0022500491&playerId=1641708",
          "gameId": "0022500491",
          "eventId": 396.0,
          "display": "44.5%",
          "body": "NBA 中国官网这次出手的原始数值为 0.445，换算显示为 44.5%。这是机会质量的参考，不是球员的个人命中保证。",
          "sourceLabel": "NBA 中国 · 逐次出手数据",
          "title": "这次出手的预期投篮命中率",
          "value": 0.445
        },
        {
          "sourceLabel": "NBA.com · 本场名单",
          "gameId": "0022500491",
          "playerId": "1641708",
          "sourceUrl": "https://www.nba.com/game/hou-vs-dal-0022500491/play-by-play",
          "title": "本场身份与号码核对",
          "kind": "official",
          "id": "amen-roster",
          "body": "NBA 本场名单：火箭 1 号为阿门·汤普森，7 号为凯文·杜兰特；独行侠 00 号为马克斯·克里斯蒂。",
          "sourcePath": "game.homeTeamPlayers / game.awayTeamPlayers",
          "description": "NBA 本场名单：火箭 1 号为阿门·汤普森，7 号为凯文·杜兰特；独行侠 00 号为马克斯·克里斯蒂。"
        },
        {
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-12s.jpg",
          "description": "本次实际输入帧",
          "timeSeconds": 12.0,
          "id": "frame-12000",
          "title": "本次实际输入帧",
          "kind": "video_frame",
          "timestampMs": 12000.0,
          "sourceLabel": "原始视频抽帧",
          "videoTime": 12.0
        },
        {
          "title": "本次实际输入帧",
          "timeSeconds": 15.0,
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-15s.jpg",
          "description": "本次实际输入帧",
          "sourceLabel": "原始视频抽帧",
          "videoTime": 15.0,
          "id": "frame-15000",
          "kind": "video_frame",
          "timestampMs": 15000.0
        },
        {
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-16.0s.jpg",
          "timeSeconds": 16.0,
          "timestampMs": 16000.0,
          "videoTime": 16.0,
          "id": "frame-16000",
          "title": "本次实际输入帧",
          "kind": "video_frame",
          "sourceLabel": "原始视频抽帧",
          "description": "本次实际输入帧"
        },
        {
          "description": "本次实际输入帧",
          "kind": "video_frame",
          "timeSeconds": 17.0,
          "sourceLabel": "原始视频抽帧",
          "timestampMs": 17000.0,
          "id": "frame-17000",
          "title": "本次实际输入帧",
          "videoTime": 17.0,
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-17.0s.jpg"
        },
        {
          "id": "frame-17500",
          "kind": "video_frame",
          "timestampMs": 17500.0,
          "videoTime": 17.5,
          "sourceLabel": "原始视频抽帧",
          "timeSeconds": 17.5,
          "title": "本次实际输入帧",
          "description": "本次实际输入帧",
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-17.5s.jpg"
        },
        {
          "frameUrl": "https://d2x8td5d05xg8h.cloudfront.net/frames/amen-18s.jpg",
          "timeSeconds": 18.0,
          "kind": "video_frame",
          "id": "frame-18000",
          "videoTime": 18.0,
          "timestampMs": 18000.0,
          "sourceLabel": "原始视频抽帧",
          "description": "本次实际输入帧",
          "title": "本次实际输入帧"
        }
      ],
      "trace": [
        {
          "step": 1.0,
          "round": 1.0,
          "tool": "inspect_frames",
          "status": "succeeded",
          "elapsedMs": 585.0
        },
        {
          "step": 2.0,
          "round": 1.0,
          "tool": "read_official_event",
          "status": "succeeded",
          "elapsedMs": 31.0
        },
        {
          "step": 3.0,
          "round": 2.0,
          "tool": "validate_story",
          "status": "succeeded",
          "elapsedMs": 2.0
        }
      ]
    }
  }
];
