"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ts = require("../node_modules/typescript");

const sourcePath = path.join(
  __dirname,
  "../src/app/capture/processing-center/promotion/page.tsx"
);

const source = fs.readFileSync(sourcePath, "utf8");

const sourceFile = ts.createSourceFile(
  "page.tsx",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX
);

const handlers = [];

function visit(node) {
  if (
    ts.isFunctionDeclaration(node) &&
    node.name?.text === "promoteSelectedJsonToCyber2"
  ) {
    handlers.push(node);
  }
  ts.forEachChild(node, visit);
}

visit(sourceFile);

assert.equal(
  handlers.length,
  1,
  "Expected exactly one existing JSON promotion handler"
);

const compiled = ts.transpileModule(
  handlers[0].getText(sourceFile),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.None,
    },
  }
).outputText;

async function scenario(count, failures = new Set(), invalid = new Set()) {
  const docs = Array.from({ length: count }, (_, index) => ({
    doc_id: `INSYT${String(index + 1).padStart(9, "0")}`,
    destination: "json_cyber2",
    classification: "HIT",
    cyber2_sent: false,
    ready_for_promotion: true,
  }));

  let active = 0;
  let maximumActive = 0;
  let calls = [];
  let error = "";
  let message = "";
  let selection = null;
  let refreshed = 0;
  let promoting = null;

  const context = {
    clientId: "TEST_CLIENT",
    projectId: "TEST_PROJECT",
    workspace: "capture",
    jsonHits: docs,
    selectedJsonIds: new Set(docs.map((doc) => doc.doc_id)),
    promotingJson: false,

    setPromotingJson(value) {
      promoting = value;
    },

    setError(value) {
      error = value;
    },

    setJsonResultMessage(value) {
      message = value;
    },

    setSelectedJsonIds(value) {
      selection = value;
    },

    async loadPromotionPopulation(force) {
      assert.equal(force, true);
      refreshed++;
    },

    async apiPost(url, body) {
      assert.match(url, /send-json-native-cyber2$/);
      assert.equal(body.client, "TEST_CLIENT");
      assert.equal(body.project, "TEST_PROJECT");
      assert.equal(body.doc_ids.length, 1);

      const id = body.doc_ids[0];
      calls.push(id);
      active++;
      maximumActive = Math.max(maximumActive, active);

      try {
        await new Promise((resolve) => setTimeout(resolve, 5));

        if (failures.has(id)) {
          throw new Error("Synthetic API failure");
        }

        return {
          status: "completed",
          verified: true,
          files_verified: true,
          cyber2_verified: !invalid.has(id),
          registration_status: "registered_verified",
          sent_count: 1,
          doc_id: id,
          source_profile: "plain",
          csv_generated: false,
          intake_index_path: `test/${id}`,
        };
      } finally {
        active--;
      }
    },
  };

  await vm.runInNewContext(
    compiled + "\npromoteSelectedJsonToCyber2();",
    context
  );

  assert.equal(active, 0);
  assert.equal(refreshed, count ? 1 : 0);
  assert.equal(promoting, count ? false : null);

  assert.equal(calls.length, count);
  assert.equal(new Set(calls).size, count);

  assert.ok(
    maximumActive <= 4,
    `Concurrency exceeded limit: ${maximumActive}`
  );

  assert.equal(maximumActive, Math.min(count, 4));

  const expectedFailed = new Set([...failures, ...invalid]);

  if (count) {
    assert.ok(selection !== null);
    assert.equal(typeof selection.has, "function");
    assert.equal(typeof selection.size, "number");
    assert.deepEqual(
      [...selection].sort(),
      [...expectedFailed].sort()
    );

    assert.match(
      message,
      new RegExp(`${count - expectedFailed.size} JSON document`)
    );
  }

  if (expectedFailed.size) {
    assert.match(error, /failed/);
  } else {
    assert.equal(error, "");
  }

  return {
    count,
    maximumActive,
    failed: expectedFailed.size,
  };
}

async function main() {
  const first = await scenario(20);
  console.log(
    `PASS: ${first.count} requests; peak ${first.maximumActive}`
  );

  const second = await scenario(
    20,
    new Set(["INSYT000000003"]),
    new Set(["INSYT000000008"])
  );

  assert.equal(second.failed, 2);
  console.log(
    "PASS: API failure and invalid verification isolated"
  );

  const third = await scenario(2);
  assert.equal(third.maximumActive, 2);
  console.log("PASS: Small batch uses only two workers");

  const fourth = await scenario(1);
  assert.equal(fourth.maximumActive, 1);
  console.log("PASS: Single-document promotion preserved");

  console.log(
    "\nPASS: ALL JSON PROMOTION CONCURRENCY REGRESSIONS"
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
