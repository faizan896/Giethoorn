//! Exact bounded financial arithmetic. Unsupported precision fails; never round.
use std::{fmt, str::FromStr};

use anyhow::{Context, Result, ensure};
use rust_decimal::Decimal;
use serde::{Deserialize, Deserializer, Serialize, Serializer};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct Amount(Decimal);

impl Amount {
    pub const ZERO: Self = Self(Decimal::ZERO);

    pub fn positive(self) -> bool {
        self > Self::ZERO
    }
    pub fn negative(self) -> bool {
        self < Self::ZERO
    }
    pub fn abs(self) -> Self {
        Self(self.0.abs())
    }
    pub fn negated(self) -> Self {
        Self(-self.0)
    }

    pub fn add_exact(self, other: Self) -> Result<Self> {
        let scale = self.0.scale().max(other.0.scale());
        let left = self
            .0
            .mantissa()
            .checked_mul(10_i128.pow(scale - self.0.scale()))
            .context("exact addition coefficient overflow")?;
        let right = other
            .0
            .mantissa()
            .checked_mul(10_i128.pow(scale - other.0.scale()))
            .context("exact addition coefficient overflow")?;
        from_parts(
            left.checked_add(right).context("exact addition overflow")?,
            scale,
        )
    }

    pub fn subtract_exact(self, other: Self) -> Result<Self> {
        self.add_exact(other.negated())
    }

    pub fn multiply_exact(self, other: Self) -> Result<Self> {
        from_parts(
            self.0
                .mantissa()
                .checked_mul(other.0.mantissa())
                .context("exact multiplication coefficient overflow")?,
            self.0.scale() + other.0.scale(),
        )
    }
}

fn from_parts(mut coefficient: i128, mut scale: u32) -> Result<Amount> {
    if coefficient == 0 {
        return Ok(Amount::ZERO);
    }
    while scale > 0 && coefficient % 10 == 0 {
        coefficient /= 10;
        scale -= 1;
    }
    ensure!(scale <= 28, "financial result exceeds exact decimal scale");
    Ok(Amount(
        Decimal::try_from_i128_with_scale(coefficient, scale)
            .context("financial result exceeds exact decimal coefficient")?,
    ))
}

impl FromStr for Amount {
    type Err = anyhow::Error;
    fn from_str(value: &str) -> Result<Self> {
        let digits = value.strip_prefix('-').unwrap_or(value);
        ensure!(
            !digits.is_empty() && digits.bytes().all(|c| c.is_ascii_digit() || c == b'.'),
            "financial values must be plain decimal strings"
        );
        Ok(Self(
            Decimal::from_str_exact(value)
                .context("financial value exceeds exact decimal precision")?
                .normalize(),
        ))
    }
}

impl fmt::Display for Amount {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0.normalize())
    }
}

impl Serialize for Amount {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&self.to_string())
    }
}

impl<'de> Deserialize<'de> for Amount {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        String::deserialize(deserializer)?
            .parse()
            .map_err(serde::de::Error::custom)
    }
}

impl Default for Amount {
    fn default() -> Self {
        Self::ZERO
    }
}
